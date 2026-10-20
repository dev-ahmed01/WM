"""Small, opt-in warehouse pilot feedback API with no free-text collection."""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, model_validator
from starlette.concurrency import run_in_threadpool

from app.core.config import settings
from app.middleware.rbac_middleware import require_role
from app.repositories.pilot_repository import PilotFeedbackRepository

router = APIRouter(prefix="/pilot", tags=["Pilot"])

Surface = Literal["reference", "workflow", "voice"]
Verdict = Literal["helpful", "needs_review"]
Issue = Literal["none", "incorrect_guidance", "missing_evidence", "unsafe_step", "voice_transcript", "other"]


class PilotFeedbackRequest(BaseModel):
    surface: Surface
    verdict: Verdict
    issue: Issue

    @model_validator(mode="after")
    def enforce_issue(self):
        if (self.verdict == "helpful") != (self.issue == "none"):
            raise ValueError("Helpful requires no issue; needs_review requires an issue")
        return self


def _enabled(department_id: str) -> bool:
    return settings.PILOT_FEEDBACK_ENABLED and department_id in {
        part.strip() for part in settings.PILOT_ALLOWED_DEPARTMENTS.split(",")
        if part.strip()
    }


def _require_pilot(department_id: str) -> None:
    if not _enabled(department_id):
        # Reveal neither whether a different department is enrolled nor
        # the contents of a pilot still under private evaluation.
        raise HTTPException(status_code=404, detail={
            "error_code": "PILOT_DISABLED", "message": "Pilot feedback is unavailable."
        })


@router.get("/config")
async def pilot_config(
    user: dict = Depends(require_role("admin", "manager", "employee")),
) -> dict:
    return {
        "feedback_enabled": bool(_enabled(str(user.get("department_id") or ""))),
        "raw_content_collection": False,
    }


@router.post("/feedback", status_code=201)
async def submit_feedback(
    payload: PilotFeedbackRequest,
    user: dict = Depends(require_role("admin", "manager", "employee")),
) -> dict:
    dept = str(user.get("department_id") or "")
    reporter = str(user.get("sub") or "")
    _require_pilot(dept)
    if not reporter:
        raise HTTPException(401, detail={"error_code": "PILOT_AUTH", "message": "Account required."})
    try:
        saved = await run_in_threadpool(
            PilotFeedbackRepository.save, dept, reporter, payload.surface,
            payload.verdict, payload.issue, settings.PILOT_FEEDBACK_MAX_PER_USER_PER_DAY,
        )
    except Exception as exc:
        raise HTTPException(503, detail={
            "error_code": "PILOT_STORE_UNAVAILABLE",
            "message": "Could not save pilot feedback. Please retry.",
        }) from exc
    if not saved:
        raise HTTPException(429, detail={
            "error_code": "PILOT_DAILY_LIMIT",
            "message": "Today's pilot feedback limit has been reached.",
        })
    return {"id": saved, "saved": True}


@router.get("/summary")
async def pilot_summary(
    days: int = Query(default=14, ge=1, le=30),
    user: dict = Depends(require_role("admin", "manager")),
) -> dict:
    dept = str(user.get("department_id") or "")
    _require_pilot(dept)
    try:
        return await run_in_threadpool(PilotFeedbackRepository.summary, dept, days)
    except Exception as exc:
        raise HTTPException(503, detail={
            "error_code": "PILOT_SUMMARY_UNAVAILABLE",
            "message": "Pilot summary is unavailable.",
        }) from exc
