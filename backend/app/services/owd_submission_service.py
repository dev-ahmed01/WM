"""Approve-and-publish for direct OWD uploads.

Everything happens in ONE transaction: lock the submission, re-validate the exact stored bytes,
compile and load the workflow, mark the submission published. Any failure rolls back, leaving the
submission pending and nothing live. The uploader can never approve their own file.
"""
from __future__ import annotations

import hashlib
import logging
from uuid import uuid4

from app.compiler.exceptions import OWDParsingException
from app.compiler.parser import OWDParser
from app.compiler.pipeline import OWDCompilerPipeline
from app.compiler.utils import generate_deterministic_uuid
from app.compiler.validator import OWDValidator
from app.core.database import get_postgres_connection
from app.integrations.ai_gateway import AIGateway
from app.repositories.owd_submission_repository import OwdSubmissionRepository, SubmissionConflict

logger = logging.getLogger("workmate.owd_submissions")


def approve_and_publish(department: str, manager: str, submission_id: str) -> dict:
    with get_postgres_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("BEGIN")
            cur.execute("SELECT set_config('workmate.department_id',%s,true)", (department,))
            try:
                sub = OwdSubmissionRepository.get_locked(cur, department, submission_id)
                if sub["status"] != "pending":
                    raise SubmissionConflict("This submission was already decided.")
                if sub["uploaded_by"] == manager:
                    raise SubmissionConflict("You cannot approve a file you uploaded.")
                text = sub["content"].decode("utf-8-sig")
                try:
                    doc = OWDParser.parse(markdown_text=text, title=sub["title"], department_id=department, default_version=1)
                except OWDParsingException as exc:
                    raise SubmissionConflict(f"The stored file no longer parses: {exc.message}") from exc
                report = OWDValidator.validate(doc)
                if not report.is_valid:
                    raise SubmissionConflict("The stored file failed validation: " + "; ".join(report.errors[:3]))
                declared = {
                    str(getattr(getattr(doc, "metadata", None), "department", "") or ""),
                    str(getattr(getattr(doc, "user_context", None), "department", "") or ""),
                } - {""}
                if declared - {department}:
                    raise SubmissionConflict("The file declares a different department than the one it was uploaded to.")
                cur.execute("SELECT is_active FROM security.departments WHERE id=%s", (department,))
                row = cur.fetchone()
                if not row or not row[0]:
                    raise SubmissionConflict("The department is not active for publishing.")
                code = doc.workflow.workflow_code
                workflow_id = generate_deterministic_uuid("workflow", code)
                cur.execute("SELECT COALESCE(MAX(version_number),0)+1 FROM knowledge_studio.workflow_versions WHERE workflow_id=%s",
                            (workflow_id,))
                version = int(cur.fetchone()[0])
                doc.workflow.version_number = version
                raw = sub["content"]
                source_id = uuid4().hex
                cur.execute("INSERT INTO shared.source_objects (id,department_id,filename,sha256_hash,content) VALUES (%s,%s,%s,%s,%s)",
                            (source_id, department, sub["filename"], hashlib.sha256(raw).hexdigest(), raw))
                result = OWDCompilerPipeline.process_owd(
                    markdown_text=text, title=sub["title"], department_id=department, user_id=sub["uploaded_by"],
                    stage_file_uri="pgobj:" + source_id, version_number=version, prepared_document=doc,
                    source_filename=sub["filename"], load_connection=conn,
                )
                if result.get("compilation_status") != "SUCCESS" or result.get("deployment_status") != "PUBLISHED":
                    raise SubmissionConflict("The compiler did not publish the file: "
                                             + "; ".join(result.get("validation_errors", [])[:3]))
                published = OwdSubmissionRepository.mark_published(cur, submission_id, manager, result["version_id"])
                cur.execute("COMMIT")
            except Exception:
                cur.execute("ROLLBACK")
                raise
    try:
        AIGateway.invalidate_all()
    except Exception:
        logger.warning("Cache invalidation after approved upload failed", exc_info=True)
    published["version_number"] = version
    published["workflow_id"] = workflow_id
    return published
