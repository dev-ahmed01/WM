# FastAPI Router for Escalation Management (Admin / Manager Read Access)

from typing import List
from fastapi import APIRouter, Depends, Query
from app.models.escalation import EscalationResponse, EscalationResolve
from app.services.escalation import EscalationService
from starlette.concurrency import run_in_threadpool
from fastapi import HTTPException
from app.middleware.rbac_middleware import require_role
from app.repositories.escalation_repository import ScopedEscalationRepository
from app.repositories.org_repository import organization_of_user
from app.core.database import get_postgres_connection

router = APIRouter(prefix="/escalations", tags=["Escalations"])

def get_escalation_service() -> EscalationService:
    return EscalationService()


def _scope(user):
    """Organization from the database; managers are additionally pinned to their department."""
    with get_postgres_connection() as conn, conn.cursor() as cur:
        org = organization_of_user(cur, user["sub"])
    dept = None if user.get("role") == "admin" else user.get("department_id")
    return org, dept


@router.get("", response_model=List[EscalationResponse], summary="List escalations in your scope")
async def list_escalations(limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0),
                           user=Depends(require_role(["admin", "manager"]))):
    org, dept = await run_in_threadpool(_scope, user)
    if not org:
        raise HTTPException(403, detail={"error_code": "ORG_NOT_CONFIGURED", "message": "No organization scope."})
    return await run_in_threadpool(ScopedEscalationRepository.list_scoped, org, dept, limit, offset)


@router.post("/{escalation_id}/resolve", summary="Resolve an escalation in your scope")
async def resolve_escalation(escalation_id: str, payload: EscalationResolve,
                             user=Depends(require_role(["admin", "manager"]))):
    org, dept = await run_in_threadpool(_scope, user)
    if not org:
        raise HTTPException(403, detail={"error_code": "ORG_NOT_CONFIGURED", "message": "No organization scope."})
    ok = await run_in_threadpool(ScopedEscalationRepository.resolve_scoped,
                                 escalation_id, payload.resolution_note, org, dept)
    if not ok:
        raise HTTPException(404, detail={"error_code": "NOT_FOUND", "message": "Escalation not found in your scope."})
    return {"message": "Escalation resolved successfully", "escalation_id": escalation_id}
