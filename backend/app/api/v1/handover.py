"""Owner-submitted operational handovers and manager acknowledgment.

This API never marks a workflow step complete, never sends a handover automatically,
and never treats acknowledgment as approval of safety-critical operations.
"""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, model_validator
from starlette.concurrency import run_in_threadpool

from app.middleware.rbac_middleware import require_role
from app.repositories.handover_repository import HandoverRepository

router = APIRouter(prefix="/handover", tags=["Shift Handover"])

Disposition = Literal["pending_next_shift", "blocked_supervisor", "information", "follow_up"]
ExceptionType = Literal["none", "damage", "quantity_mismatch", "missing_document", "safety_concern", "other"]
Severity = Literal["normal", "high", "critical"]
Decision = Literal["acknowledged", "follow_up_requested"]


class HandoverSubmission(BaseModel):
    model_config = ConfigDict(extra="forbid")
    conversation_id: str = Field(min_length=1, max_length=64)
    recipient_label: str = Field(min_length=2, max_length=100)
    disposition: Disposition
    exception_type: ExceptionType = "none"
    severity: Severity = "normal"
    next_action: str = Field(min_length=5, max_length=1500)
    notes: str = Field(default="", max_length=1500)

    @model_validator(mode="after")
    def valid_issue(self):
        if self.severity == "critical" and self.exception_type == "none":
            raise ValueError("A critical handover must identify an exception category")
        if self.exception_type == "safety_concern" and self.disposition == "information":
            raise ValueError("A safety concern cannot be information-only")
        return self


class ReviewSubmission(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: Decision
    review_note: str = Field(min_length=8, max_length=1000)


@router.post("", status_code=201)
async def submit_handover(
    payload: HandoverSubmission,
    user: dict = Depends(require_role("admin", "employee", "manager")),
) -> dict:
    dept, actor = str(user.get("department_id") or ""), str(user.get("sub") or "")
    if not dept or not actor:
        raise HTTPException(401, detail={"error_code": "HANDOVER_AUTH_REQUIRED"})
    try:
        record = await run_in_threadpool(
            HandoverRepository.submit, dept, actor, payload.conversation_id,
            payload.recipient_label.strip(), payload.disposition, payload.exception_type,
            payload.severity, payload.next_action.strip(), payload.notes.strip(),
        )
    except Exception as exc:
        raise HTTPException(503, detail={
            "error_code": "HANDOVER_STORE_UNAVAILABLE",
            "message": "Could not save the handover. No workflow state was modified.",
        }) from exc
    if not record:
        # Same answer for unauthorized cross-department and unknown sessions.
        raise HTTPException(404, detail={"error_code": "SESSION_UNAVAILABLE"})
    return record


@router.get("")
async def list_handovers(
    limit: int = Query(40, ge=1, le=100),
    user: dict = Depends(require_role("admin", "employee", "manager")),
) -> dict:
    dept, actor = str(user.get("department_id") or ""), str(user.get("sub") or "")
    reviewer = user.get("role") in ("admin", "manager")
    try:
        rows = await run_in_threadpool(HandoverRepository.list, dept, actor, reviewer, limit)
    except Exception as exc:
        raise HTTPException(503, detail={"error_code": "HANDOVER_LIST_UNAVAILABLE"}) from exc
    return {"items": rows, "reviewer": reviewer, "department_id": dept}


@router.post("/{handover_id}/review")
async def review_handover(
    handover_id: str,
    payload: ReviewSubmission,
    user: dict = Depends(require_role("admin", "manager")),
) -> dict:
    dept, actor = str(user.get("department_id") or ""), str(user.get("sub") or "")
    if not dept or not actor:
        raise HTTPException(401, detail={"error_code": "HANDOVER_AUTH_REQUIRED"})
    try:
        record = await run_in_threadpool(
            HandoverRepository.review,
            dept, actor, handover_id, payload.decision, payload.review_note.strip(),
        )
    except Exception as exc:
        raise HTTPException(503, detail={"error_code": "HANDOVER_REVIEW_UNAVAILABLE"}) from exc
    if not record:
        # Cannot review own submission, other department, or already reviewed.
        raise HTTPException(409, detail={
            "error_code": "HANDOVER_REVIEW_REJECTED",
            "message": "Review unavailable. The record may have changed or be outside your scope.",
        })
    return record
