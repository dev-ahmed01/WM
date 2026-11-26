"""Authenticated, owner-scoped workflow session lifecycle endpoints."""

from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.security import normalize_role
from app.middleware.rbac_middleware import require_role
from app.models.workflow_session import (
    AbandonSessionRequest,
    AdvanceSessionRequest,
    WorkflowAdvanceResponse,
    WorkflowSession,
)
from app.repositories.workflow_session_repository import WorkflowSessionRepository
from app.core.database import get_postgres_connection
from app.services.workflow_state import WorkflowStateService

router = APIRouter(prefix="/copilot/session", tags=["Copilot Session State"])

_authorized_user = require_role("employee", "admin", "manager")


def _same_organization(admin_id: str, owner_id: str) -> bool:
    """True only when both users belong to the same, configured organization."""
    from app.repositories.org_repository import organization_of_user
    with get_postgres_connection() as conn:
        with conn.cursor() as cur:
            a, b = organization_of_user(cur, admin_id), organization_of_user(cur, owner_id)
    return bool(a) and a == b


def _forbidden(message: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail={"error_code": "AUTH_FORBIDDEN", "message": message, "details": None},
    )


def _owned_session(session_id: str, current_user: Dict[str, Any], *, write: bool = True) -> Dict[str, Any]:
    """Owner-scoped. An administrator may READ sessions inside their own organization (supervision);
    nobody but the owner may change a session, because advancing steps is an attestation by that person.
    Foreign sessions answer exactly like missing ones."""
    session = WorkflowSessionRepository.get_by_id(session_id)
    not_found = HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={"error_code": "NOT_FOUND", "message": f"Workflow session '{session_id}' not found.", "details": None},
    )
    if not session:
        raise not_found
    me, owner = str(current_user.get("sub") or ""), str(session.get("user_id") or "")
    if owner != me:
        is_admin = normalize_role(current_user.get("role", "")) == "admin"
        if not (is_admin and not write and _same_organization(me, owner)):
            if is_admin and write and _same_organization(me, owner):
                raise _forbidden("Only the employee who started this session can change it.")
            raise not_found
    if _task_bound(session_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error_code":"WORK_EXECUTION_ONLY",
                    "message":"Use the assigned work item to record evidence and progress."},
        )
    return session


def _task_bound(session_id: str) -> bool:
    """Check the durable task link, never a request-supplied claim."""
    with get_postgres_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM workmate_copilot.work_items WHERE execution_session_id=%s",
                (session_id,),
            )
            return cur.fetchone() is not None


@router.get("/{id}", response_model=WorkflowSession, summary="Get workflow session details")
async def get_session_endpoint(
    id: str,
    current_user: Dict[str, Any] = Depends(_authorized_user),
) -> WorkflowSession:
    return WorkflowSession(**_owned_session(id, current_user, write=False))


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


@router.post("/{id}/advance", response_model=WorkflowAdvanceResponse)
async def advance_session_endpoint(
    id: str,
    payload: AdvanceSessionRequest,
    current_user: Dict[str, Any] = Depends(_authorized_user),
) -> WorkflowAdvanceResponse:
    _owned_session(id, current_user)
    context: Dict[str, Any] = {
        "values": payload.values,
        "rule_results": payload.rule_results,
        "use_fallback": payload.use_fallback,
    }
    if payload.decision_option:
        context["decision_option"] = payload.decision_option
    session = WorkflowStateService.mark_step_complete(id, context)
    position = WorkflowStateService.get_position(session)
    return WorkflowAdvanceResponse(
        status=session.status,
        current_state_id=session.current_state_id,
        active_step_number=position.step_number,
        active_step_title=position.step_title,
        active_decision_options=position.decision_options,
    )


@router.post("/{id}/abandon", response_model=WorkflowSession)
async def abandon_session_endpoint(
    id: str,
    payload: AbandonSessionRequest,
    current_user: Dict[str, Any] = Depends(_authorized_user),
) -> WorkflowSession:
    _owned_session(id, current_user)
    return WorkflowStateService.abandon_session(id, payload.reason)
