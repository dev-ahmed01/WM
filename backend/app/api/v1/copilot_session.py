"""FastAPI Router for Copilot Session State Operations."""

from fastapi import APIRouter, Depends, HTTPException, status
from app.models.workflow_session import WorkflowSession, AbandonSessionRequest
from app.repositories.workflow_session_repository import WorkflowSessionRepository
from app.services.workflow_state import WorkflowStateService
from app.middleware.rbac_middleware import require_role

router = APIRouter(prefix="/copilot/session", tags=["Copilot Session State"])


@router.get(
    "/{id}",
    response_model=WorkflowSession,
    summary="Get workflow session details",
    dependencies=[Depends(require_role("employee", "admin", "manager"))],
)
async def get_session_endpoint(id: str) -> WorkflowSession:
    """Retrieves current details and step position of a workflow session."""
    session_dict = WorkflowSessionRepository.get_by_id(id)
    if not session_dict:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error_code": "NOT_FOUND", "message": f"Workflow session '{id}' not found.", "details": None},
        )
    return WorkflowSession(**session_dict)


@router.post(
    "/{id}/resume",
    response_model=WorkflowSession,
    summary="Resume a paused workflow session",
    dependencies=[Depends(require_role("employee", "admin", "manager"))],
)
async def resume_session_endpoint(id: str) -> WorkflowSession:
    """Resumes a paused workflow session back to active status."""
    return WorkflowStateService.resume_session(session_id=id)


@router.post(
    "/{id}/pause",
    response_model=WorkflowSession,
    summary="Pause an active workflow session",
    dependencies=[Depends(require_role("employee", "admin", "manager"))],
)
async def pause_session_endpoint(id: str) -> WorkflowSession:
    """Pauses an active workflow session."""
    return WorkflowStateService.pause_session(session_id=id)


@router.post(
    "/{id}/abandon",
    response_model=WorkflowSession,
    summary="Abandon an active workflow session",
    dependencies=[Depends(require_role("employee", "admin", "manager"))],
)
async def abandon_session_endpoint(
    id: str,
    payload: AbandonSessionRequest,
) -> WorkflowSession:
    """Abandons an active workflow session with an audit reason."""
    return WorkflowStateService.abandon_session(session_id=id, reason=payload.reason)
