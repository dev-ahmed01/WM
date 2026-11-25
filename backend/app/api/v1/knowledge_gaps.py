"""Knowledge-gap console and manager approvals: the closed loop from an
unanswered employee question to an approved, published SOP.

A supervisor/admin reply is shown to the employee as a reply, never stored as
knowledge. Only a drafted SOP that a manager approved and an admin published
becomes retrievable guidance.
"""
from __future__ import annotations

from typing import Any, Dict, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from starlette.concurrency import run_in_threadpool

from app.core.database import get_postgres_connection
from app.middleware.rbac_middleware import require_role
from app.repositories.escalation_repository import ScopedEscalationRepository
from app.repositories.knowledge_loop_repository import ApprovalRepository, GapNotFound, KnowledgeGapRepository
from app.repositories.org_repository import organization_of_user
from app.repositories.owd_submission_repository import OwdSubmissionRepository, SubmissionConflict, SubmissionNotFound
from app.repositories.procedure_draft_repository import DraftConflict, DraftNotFound, ProcedureDraftRepository
from app.services import owd_submission_service
from app.services.document_extraction import DocumentExtractionError, extract_document

router = APIRouter(tags=["Knowledge loop"])


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class GapReply(Strict):
    reply: str = Field(min_length=3, max_length=1500)


class GapDraft(Strict):
    title: str = Field(min_length=5, max_length=180)
    steps: list[str] = Field(min_length=1, max_length=30)


class Decision(Strict):
    expected_revision: int = Field(ge=1)
    decision: Literal["approve", "return"]
    note: str = Field(default="", max_length=800)


def _scope(user: Dict[str, Any]) -> tuple[str, Optional[str]]:
    with get_postgres_connection() as conn, conn.cursor() as cur:
        org = organization_of_user(cur, user["sub"])
    if not org:
        raise HTTPException(403, detail={"error_code": "ORG_NOT_CONFIGURED", "message": "No organization scope."})
    return org, (None if user.get("role") == "admin" else user.get("department_id"))


async def _guard(fn, *args):
    try:
        return await run_in_threadpool(fn, *args)
    except (GapNotFound, DraftNotFound, SubmissionNotFound) as exc:
        raise HTTPException(404, detail={"error_code": "NOT_FOUND", "message": "Not found in your scope."}) from exc
    except (DraftConflict, SubmissionConflict) as exc:
        raise HTTPException(409, detail={"error_code": "CONFLICT", "message": str(exc)}) from exc


@router.get("/knowledge-gaps/mine")
async def my_questions(user: Dict[str, Any] = Depends(require_role("employee", "manager", "admin"))):
    """The caller's own unanswered questions with any supervisor reply."""
    return {"items": await _guard(KnowledgeGapRepository.mine, user["sub"])}


@router.get("/knowledge-gaps")
async def list_gaps(status: Optional[Literal["open", "answered", "drafting", "resolved", "dismissed"]] = None,
                    limit: int = Query(100, ge=1, le=200),
                    user: Dict[str, Any] = Depends(require_role("admin", "manager"))):
    org, dept = await run_in_threadpool(_scope, user)
    return {"items": await _guard(KnowledgeGapRepository.list_scoped, org, dept, status, limit)}


@router.post("/knowledge-gaps/{gap_id}/reply")
async def reply_to_gap(gap_id: str, body: GapReply, user: Dict[str, Any] = Depends(require_role("admin", "manager"))):
    org, dept = await run_in_threadpool(_scope, user)
    gap = await _guard(KnowledgeGapRepository.reply, org, dept, gap_id, user["sub"], body.reply.strip())
    if gap.get("escalation_id"):
        # The human response closes the support case; it does not create knowledge.
        await run_in_threadpool(ScopedEscalationRepository.resolve_scoped, gap["escalation_id"],
                                "Replied to the employee: " + body.reply.strip()[:400], org, dept)
    return gap


@router.post("/knowledge-gaps/{gap_id}/dismiss")
async def dismiss_gap(gap_id: str, user: Dict[str, Any] = Depends(require_role("admin"))):
    org, dept = await run_in_threadpool(_scope, user)
    return await _guard(KnowledgeGapRepository.dismiss, org, dept, gap_id)


def _create_draft(gap: Dict[str, Any], actor: str, title: str, steps: list[str]) -> Dict[str, Any]:
    body = "\n".join(f"{i}. {s.strip()}" for i, s in enumerate(steps, 1) if s.strip())
    raw = (title + "\n\nProposed from an unanswered employee question (needs review):\n" + body + "\n").encode("utf-8")
    try:
        extracted = extract_document("gap-proposal.txt", raw)
    except DocumentExtractionError as exc:
        raise DraftConflict(str(exc)) from exc
    draft = ProcedureDraftRepository.create(gap["department_id"], actor, extracted, raw, title)
    KnowledgeGapRepository.link_draft(gap["id"], draft["id"])
    return draft


@router.post("/knowledge-gaps/{gap_id}/draft", status_code=201)
async def draft_from_gap(gap_id: str, body: GapDraft, user: Dict[str, Any] = Depends(require_role("admin"))):
    """Turn a gap into an editable, UNPUBLISHED draft in Procedure Studio."""
    org, dept = await run_in_threadpool(_scope, user)
    gap = await _guard(KnowledgeGapRepository.get, org, dept, gap_id)
    if gap["status"] in ("resolved", "dismissed") or gap.get("draft_id"):
        raise HTTPException(409, detail={"error_code": "CONFLICT", "message": "This question is closed or already has a draft."})
    draft = await _guard(_create_draft, gap, user["sub"], body.title.strip(), body.steps)
    return {"draft_id": draft["id"], "status": draft["status"], "steps": len(draft.get("steps", []))}


@router.get("/procedure/approvals")
async def pending_approvals(user: Dict[str, Any] = Depends(require_role("manager"))):
    uploads = await _guard(OwdSubmissionRepository.list_for_departments, [user["department_id"]], "pending")
    return {"items": await _guard(ApprovalRepository.pending, user["department_id"]), "uploads": uploads}


@router.post("/procedure/approvals/{draft_id}")
async def decide_approval(draft_id: str, body: Decision, user: Dict[str, Any] = Depends(require_role("manager"))):
    if body.decision == "return" and len(body.note.strip()) < 8:
        raise HTTPException(422, detail={"error_code": "NOTE_REQUIRED", "message": "Say what needs to change (at least 8 characters)."})
    result = await _guard(ApprovalRepository.decide, user["department_id"], user["sub"], draft_id,
                          body.expected_revision, body.decision == "approve", body.note.strip())
    return {"draft_id": draft_id, "status": result["status"], "revision": result["revision"],
            "approved": result["approved_by"] is not None}


class UploadDecision(Strict):
    decision: Literal["approve", "return"]
    note: str = Field(default="", max_length=800)


@router.post("/procedure/approvals/uploads/{submission_id}")
async def decide_upload(submission_id: str, body: UploadDecision, user: Dict[str, Any] = Depends(require_role("manager"))):
    """Approve = compile and publish exactly the stored file (one transaction); return = send back with a note."""
    dept, manager = user["department_id"], user["sub"]
    if body.decision == "return":
        if len(body.note.strip()) < 8:
            raise HTTPException(422, detail={"error_code": "NOTE_REQUIRED", "message": "Say what needs to change (at least 8 characters)."})
        row = await _guard(OwdSubmissionRepository.mark_returned, dept, manager, submission_id, body.note.strip())
        return {"id": row["id"], "status": row["status"]}
    row = await _guard(owd_submission_service.approve_and_publish, dept, manager, submission_id)
    return {"id": row["id"], "status": row["status"], "version_number": row["version_number"],
            "knowledge_item_id": row["workflow_id"]}
