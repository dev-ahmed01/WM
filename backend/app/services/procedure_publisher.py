"""Explicit admin publication of an already-reviewed, immutable draft revision.

Uses the same OWDParser/Validator/Compiler/Loader path as hand-authored OWD.
The visual editor never writes executable graph tables directly.
"""
from __future__ import annotations

import hashlib
from uuid import uuid4
from app.core.database import get_postgres_connection
from app.repositories.procedure_draft_repository import (
    ProcedureDraftRepository,DraftNotFound,DraftConflict,COLUMNS,_dict,_event,_start,
)
from app.services.procedure_plan import (
    ProcedurePlanError,compile_preview,render_owd,
)
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
                    cur.execute("""
                        SELECT is_active FROM security.departments WHERE id=%s
                    """,(department,))
                    active=cur.fetchone()
                    if not active or not active[0]:
                        raise DraftConflict("Your department is not active for publishing.")
                    cur.execute("""
                        SELECT COALESCE(MAX(version_number),0)+1
                        FROM knowledge_studio.workflow_versions WHERE workflow_id=%s
                    """,(workflow_id,))
                    version=int(cur.fetchone()[0])
                    check=compile_preview(draft,version)
                    if not check["valid"]:
                        raise DraftConflict("The compiler rejected publication: "+
                                             "; ".join(check["validation_errors"][:3]))
                    raw=generated.encode("utf-8")
                    source_id=uuid4().hex
                    staged_uri="pgobj:"+source_id
                    cur.execute("""
                        INSERT INTO shared.source_objects
                        (id,department_id,filename,sha256_hash,content)
                        VALUES(%s,%s,%s,%s,%s)
                    """,(source_id,department,code+".md",hashlib.sha256(raw).hexdigest(),raw))
                    result=OWDCompilerPipeline.process_owd(
                        markdown_text=generated,title=draft["title"],
                        department_id=department,user_id=admin,
                        stage_file_uri=staged_uri,
                        source_filename=code+".md",
                        version_number=version,
                        load_connection=conn,
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
                    # Cache refresh cannot undo a committed publication.
                    try:
                        AIGateway.invalidate_department(department)
                    except Exception:
                        pass
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
                    # The original source object, compiled graph and review event
                    # participate in the same transaction and all roll back.
                    raise
