"""Authenticated, owner-scoped workflow session lifecycle endpoints."""

from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.security import normalize_role
from app.middleware.rbac_middleware import require_role
from app.models.workflow_session import (
    AbandonSessionRequest,
    AdvanceSessionRequest,
    WorkflowSession,
)
from app.repositories.workflow_session_repository import WorkflowSessionRepository
from app.services.workflow_state import WorkflowStateService

router = APIRouter(prefix="/copilot/session", tags=["Copilot Session State"])

_authorized_user = require_role("employee", "admin", "manager")


def _owned_session(session_id: str, current_user: Dict[str, Any]) -> Dict[str, Any]:
    session = WorkflowSessionRepository.get_by_id(session_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error_code": "NOT_FOUND",
                "message": f"Workflow session '{session_id}' not found.",
                "details": None,
            },
        )
    is_admin = normalize_role(current_user.get("role", "")) == "admin"
    if not is_admin and session.get("user_id") != current_user.get("sub"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error_code": "AUTH_FORBIDDEN",
                "message": "You do not own this workflow session.",
                "details": None,
            },
        )
    return session


@router.get("/{id}", response_model=WorkflowSession, summary="Get workflow session details")
async def get_session_endpoint(
    id: str,
    current_user: Dict[str, Any] = Depends(_authorized_user),
) -> WorkflowSession:
    return WorkflowSession(**_owned_session(id, current_user))


@router.post("/{id}/resume", response_model=WorkflowSession)
async def resume_session_endpoint(
    id: str,
    current_user: Dict[str, Any] = Depends(_authorized_user),
) -> WorkflowSession:
    _owned_session(id, current_user)
    return WorkflowStateService.resume_session(id)


@router.post("/{id}/pause", response_model=WorkflowSession)
async def pause_session_endpoint(
    id: str,
    current_user: Dict[str, Any] = Depends(_authorized_user),
) -> WorkflowSession:
    _owned_session(id, current_user)
    return WorkflowStateService.pause_session(id)


@router.post("/{id}/advance", response_model=WorkflowSession)
async def advance_session_endpoint(
    id: str,
    payload: AdvanceSessionRequest,
    current_user: Dict[str, Any] = Depends(_authorized_user),
) -> WorkflowSession:
    _owned_session(id, current_user)
    context: Dict[str, Any] = {
        "values": payload.values,
        "rule_results": payload.rule_results,
        "use_fallback": payload.use_fallback,
    }
    if payload.decision_option:
        context["decision_option"] = payload.decision_option
    return WorkflowStateService.mark_step_complete(id, context)


@router.post("/{id}/abandon", response_model=WorkflowSession)
async def abandon_session_endpoint(
    id: str,
    payload: AbandonSessionRequest,
    current_user: Dict[str, Any] = Depends(_authorized_user),
) -> WorkflowSession:
    _owned_session(id, current_user)
    return WorkflowStateService.abandon_session(id, payload.reason)
