"""Test answer: show an administrator what the assistant would find for a question, without creating a conversation,
a workflow session, an escalation or any analytics event. Published knowledge only: drafts are never used by the assistant."""
from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from starlette.concurrency import run_in_threadpool

from app.core.database import get_postgres_connection
from app.middleware.rbac_middleware import require_role
from app.repositories.knowledge_repository import KnowledgeRepository
from app.repositories.org_repository import organization_of_user
from app.services.workflow_intent import PROPOSAL_MIN_SCORE, WorkflowIntentService

router = APIRouter(prefix="/knowledge", tags=["Knowledge"])


class TestAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str = Field(min_length=3, max_length=500)
    department_id: str = Field(min_length=1, max_length=64)


def _run(user: Dict[str, Any], body: TestAnswer) -> Dict[str, Any]:
    with get_postgres_connection() as conn, conn.cursor() as cur:
        org = organization_of_user(cur, user["sub"])
        cur.execute("SELECT 1 FROM security.departments WHERE id=%s AND organization_id=%s", (body.department_id, org))
        if not org or not cur.fetchone():
            raise HTTPException(404, detail={"error_code": "NOT_FOUND", "message": "Department not found in your organization."})
    catalog = KnowledgeRepository.list_published_catalog(body.department_id)
    ranked = WorkflowIntentService.rank_published_workflows(body.question, catalog, limit=3)
    matches = [{"title": str(m.get("title")), "description": str(m.get("description") or ""), "score": round(float(m.get("match_score") or 0.0), 2),
                "would_be_offered": float(m.get("match_score") or 0.0) >= PROPOSAL_MIN_SCORE} for m in ranked]
    top = matches[0] if matches else None
    return {
        "question": body.question,
        "outcome": "answers" if top and top["would_be_offered"] else "no_approved_answer",
        "explanation": ("The assistant would offer this approved procedure." if top and top["would_be_offered"]
                        else "No approved procedure matches well enough. The assistant would say so and open a request for a person, rather than guess."),
        "matches": matches,
        "note": "Only published procedures are used. Drafts and documents waiting for approval are not visible to the assistant.",
    }


@router.post("/test-answer")
async def test_answer(body: TestAnswer, user: Dict[str, Any] = Depends(require_role("admin"))):
    return await run_in_threadpool(_run, user, body)
