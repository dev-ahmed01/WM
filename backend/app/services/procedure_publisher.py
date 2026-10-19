"""Explicit admin publication of an already-reviewed, immutable draft revision.

Uses the same OWDParser/Validator/Compiler/Loader path as hand-authored OWD.
The visual editor never writes executable graph tables directly.
"""
from __future__ import annotations

import hashlib
from app.core.database import get_postgres_connection
from app.repositories.procedure_draft_repository import (
    ProcedureDraftRepository,DraftNotFound,DraftConflict,COLUMNS,_dict,_event,_start,
)
from app.repositories.knowledge_repository import KnowledgeRepository
from app.services.procedure_plan import (
    ProcedurePlanError,compile_preview,render_owd,
)
from app.services.ingestion import IngestionService
from app.compiler.pipeline import OWDCompilerPipeline
from app.compiler.utils import generate_deterministic_uuid
from app.integrations.ai_gateway import AIGateway


class ProcedurePublisher:
    @staticmethod
    def preview(department,draft_id):
        draft=ProcedureDraftRepository.get(department,draft_id)
        try:
            result=compile_preview(draft)
        except ProcedurePlanError as exc:
            raise DraftConflict(str(exc)) from exc
        # A valid syntax preview is not sufficient to authorize publication.
        result["can_publish"]=(result["valid"] and draft["status"]=="reviewed"
                               and draft["published_version_id"] is None)
        result["review_revision"]=draft["revision"]
        result["workflow_code"]="SOP_DRAFT_"+draft["id"].split("_",1)[-1].upper()
        return result

    @staticmethod
    def publish(department,admin,draft_id,expected_revision,approval):
        if approval != "PUBLISH_REVIEWED_SOP":
            raise DraftConflict("An explicit administrator publishing confirmation is required.")
        staged_uri=None
        with get_postgres_connection() as conn:
            with conn.cursor() as cur:
                _start(cur,department)
                try:
                    cur.execute("""SELECT """+COLUMNS+"""
                        FROM knowledge_studio.procedure_drafts
                        WHERE id=%s AND department_id=%s FOR UPDATE
                    """,(draft_id,department))
                    draft=_dict(cur)
                    if not draft:
                        raise DraftNotFound()
                    if (draft["revision"]!=expected_revision or
                        draft["status"]!="reviewed" or draft["published_version_id"]):
                        raise DraftConflict("Only the unchanged, reviewed revision can be published.")
                    try:
                        generated=render_owd(draft)
                    except ProcedurePlanError as exc:
                        raise DraftConflict(str(exc)) from exc
                    code="SOP_DRAFT_"+draft_id.split("_",1)[-1].upper()
                    workflow_id=generate_deterministic_uuid("workflow",code)
                    active,version=KnowledgeRepository.get_upload_context(department,workflow_id)
                    if not active:
                        raise DraftConflict("Your department is not active for publishing.")
                    check=compile_preview(draft,version)
                    if not check["valid"]:
                        raise DraftConflict("The compiler rejected publication: "+
                                             "; ".join(check["validation_errors"][:3]))
                    raw=generated.encode("utf-8")
                    staged_uri=IngestionService.stage_file(
                        raw,code+".md",f"draft/{draft_id}/v{version}/{hashlib.sha256(raw).hexdigest()[:12]}",
                        department_id=department)
                    result=OWDCompilerPipeline.process_owd(
                        markdown_text=generated,title=draft["title"],
                        department_id=department,user_id=admin,
                        stage_file_uri=staged_uri,
                        source_filename=code+".md",
                        version_number=version,
                    )
                    if result.get("compilation_status")!="SUCCESS" or result.get("deployment_status")!="PUBLISHED":
                        raise DraftConflict("The existing OWD compiler did not publish the procedure.")
                    if result.get("workflow_id")!=workflow_id or not result.get("version_id"):
                        raise DraftConflict("Compiler returned an unexpected workflow identity.")
                    cur.execute("""UPDATE knowledge_studio.procedure_drafts
                        SET status='published',published_version_id=%s,
                            revision=revision+1,updated_at=CURRENT_TIMESTAMP
                        WHERE id=%s AND department_id=%s AND revision=%s
                          AND status='reviewed'
                        RETURNING """+COLUMNS,
                        (result["version_id"],draft_id,department,expected_revision))
                    published=_dict(cur)
                    if not published:
                        raise DraftConflict("Reviewed draft changed during publication.")
                    _event(cur,draft_id,department,admin,"published",published["revision"])
                    cur.execute("COMMIT")
                    AIGateway.invalidate_all()
                    return {
                        "draft_id":draft_id,"status":"published",
                        "workflow_id":workflow_id,
                        "version_id":result["version_id"],
                        "version_number":version,
                        "revision":published["revision"],
                        "states":result.get("number_of_states",0),
                        "steps":result.get("number_of_steps",0),
                    }
                except Exception:
                    cur.execute("ROLLBACK")
                    # The compiler loader is a separate fully transactional writer.
                    # Remove an orphan markdown object when publication fails.
                    if staged_uri:
                        try:
                            IngestionService.remove_staged_files(
                                [staged_uri],department_id=department)
                        except Exception:
                            pass
                    raise
