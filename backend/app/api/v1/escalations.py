# FastAPI Router for Escalation Management (Admin / Manager Read Access)

from typing import List
from fastapi import APIRouter, Depends, Query
from app.models.escalation import EscalationResponse, EscalationResolve
from app.services.escalation import EscalationService
from app.middleware.rbac_middleware import require_role

router = APIRouter(prefix="/escalations", tags=["Escalations"])

def get_escalation_service() -> EscalationService:
    return EscalationService()

@router.get(
    "",
    response_model=List[EscalationResponse],
    summary="List escalations (Admin/Manager only)",
    dependencies=[Depends(require_role(["admin", "manager"]))]
)
async def list_escalations(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    service: EscalationService = Depends(get_escalation_service)
):
    """Retrieves list of operational escalations for Intelligence Hub dashboards."""
    return service.list_escalations(limit=limit, offset=offset)

@router.post(
    "/{escalation_id}/resolve",
    summary="Resolve an escalation (Admin/Manager only)",
    dependencies=[Depends(require_role(["admin", "manager"]))]
)
async def resolve_escalation(
    escalation_id: str,
    payload: EscalationResolve,
    service: EscalationService = Depends(get_escalation_service)
):
    """Marks an escalation as resolved with supervisor resolution notes."""
    service.resolve(escalation_id=escalation_id, resolution_note=payload.resolution_note)
    return {"message": "Escalation resolved successfully", "escalation_id": escalation_id}
