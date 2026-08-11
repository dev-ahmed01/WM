"""Deterministic execution engine for compiled OWD state graphs."""

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from fastapi import HTTPException, status

from app.exceptions import WorkMateException
from app.models.workflow_session import WorkflowDecisionOption, WorkflowPosition, WorkflowSession
from app.repositories.owd_repository import OWDRepository
from app.repositories.workflow_session_repository import WorkflowSessionRepository

workflow_logger = logging.getLogger("copilot_services")


@dataclass(frozen=True)
class WorkflowCompletionResult:
    session: WorkflowSession
    completed_step_numbers: List[int] = field(default_factory=list)
    stopped_at_decision: bool = False


class WorkflowStateService:
    """Advance only persisted states, steps, and transitions from the compiled graph."""

    @staticmethod
    def _not_found(session_id: str) -> HTTPException:
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error_code": "NOT_FOUND",
                "message": f"Workflow session '{session_id}' not found.",
                "details": None,
            },
        )

    @staticmethod
    def _conflict(message: str) -> HTTPException:
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error_code": "INVALID_SESSION_STATE", "message": message, "details": None},
        )

    @staticmethod
    def get_active_session(conversation_id: str) -> Optional[WorkflowSession]:
        session = WorkflowSessionRepository.get_active_by_conversation(conversation_id)
        return WorkflowSession(**session) if session else None

    @staticmethod
    def get_current_session(conversation_id: str) -> Optional[WorkflowSession]:
        session = WorkflowSessionRepository.get_current_by_conversation(conversation_id)
        return WorkflowSession(**session) if session else None

    @staticmethod
    def start_session(
        conversation_id: str,
        workflow_version_id: str,
        user_id: str,
    ) -> WorkflowSession:
        initial_state = OWDRepository.get_initial_state(workflow_version_id)
        if not initial_state:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "error_code": "WORKFLOW_NOT_EXECUTABLE",
                    "message": "The published workflow has no initial state.",
                    "details": {"workflow_version_id": workflow_version_id},
                },
            )
        session_id = WorkflowSessionRepository.create(
            conversation_id=conversation_id,
            workflow_version_id=workflow_version_id,
            current_state_id=initial_state["id"],
            user_id=user_id,
            session_context={},
        )
        session = WorkflowSessionRepository.get_by_id(session_id)
        if not session:
            raise WorkMateException(message=f"Failed to reload workflow session '{session_id}'.")
        OWDRepository.record_analytics_event(
            session_id=session_id,
            workflow_version_id=workflow_version_id,
            event_type="SESSION_STARTED",
            state_id=initial_state["id"],
        )
        return WorkflowSession(**session)

    @staticmethod
    def get_position(session: WorkflowSession) -> WorkflowPosition:
        state = OWDRepository.get_state_by_id(session.current_state_id)
        if not state or state.get("workflow_version_id") != session.workflow_version_id:
            raise WorkMateException(
                message=f"Session '{session.id}' references an invalid workflow state."
            )
        step = OWDRepository.get_next_pending_step(session.id, session.current_state_id)
        decision_options = [
            WorkflowDecisionOption(**option)
            for option in OWDRepository.get_decision_options(session.current_state_id)
        ]
        return WorkflowPosition(
            state_id=state["id"],
            state_title=state["title"],
            state_type=state["state_type"],
            step_id=step.get("id") if step else None,
            # Compiled OWD step ordinals are persisted as one-based global
            # sequence numbers. Preserve that value for user-facing progress.
            step_number=int(step.get("ordinal_index", 0)) if step else None,
            step_title=step.get("instruction") if step else state["title"],
            expected_output_type=step.get("expected_output_type") if step else None,
            decision_options=decision_options,
        )

    @staticmethod
    def _status_after_transition(transition: Dict[str, Any]) -> str:
        """A terminal state is complete on entry only when it has no work of its own."""
        if not bool(transition.get("is_terminal")):
            return "active"
        return (
            "active"
            if OWDRepository.get_steps_for_state(transition["to_state_id"])
            else "completed"
        )

    @staticmethod
    def mark_step_complete(
        session_id: str,
        transition_context: Optional[Dict[str, Any]] = None,
    ) -> WorkflowSession:
        session_data = WorkflowSessionRepository.get_by_id(session_id)
        if not session_data:
            raise WorkflowStateService._not_found(session_id)
        if session_data["status"] != "active":
            raise WorkflowStateService._conflict("Only an active workflow session can advance.")

        current_state_id = session_data["current_state_id"]
        state = OWDRepository.get_state_by_id(current_state_id)
        if not state:
            raise WorkMateException(message=f"Workflow state '{current_state_id}' was not found.")
        pending_step = OWDRepository.get_next_pending_step(session_id, current_state_id)
        if not pending_step:
            return WorkflowStateService.advance_session(session_id, transition_context or {})

        context = {**session_data.get("session_context", {}), **(transition_context or {})}
        pending_count = OWDRepository.count_pending_steps(session_id, current_state_id)
        next_state_id: Optional[str] = None
        new_status = "active"
        if pending_count == 1:
            transition = OWDRepository.get_next_state_transition(current_state_id, context)
            if transition:
                next_state_id = transition["to_state_id"]
                new_status = WorkflowStateService._status_after_transition(transition)
            elif bool(state.get("is_terminal")):
                new_status = "completed"
            else:
                raise WorkflowStateService._conflict(
                    "The final step is complete, but no workflow transition matches the supplied context."
                )

        WorkflowSessionRepository.apply_progress(
            session_id=session_id,
            expected_state_id=current_state_id,
            expected_updated_at=session_data["updated_at"],
            session_context=context,
            step_id=pending_step["id"],
            next_state_id=next_state_id,
            new_status=new_status,
        )
        event_type = "SESSION_COMPLETED" if new_status == "completed" else "STEP_COMPLETED"
        OWDRepository.record_analytics_event(
            session_id=session_id,
            workflow_version_id=session_data["workflow_version_id"],
            event_type=event_type,
            state_id=next_state_id or current_state_id,
            step_id=pending_step["id"],
            payload=context,
        )
        return WorkflowStateService._reload(session_id)

    @staticmethod
    def complete_through_step(
        session_id: str, target_step_number: int
    ) -> WorkflowCompletionResult:
        """Record an explicit completion attestation through a numbered atomic step.

        This advances sequentially through persisted steps only. It never invents a
        branch choice and stops if the workflow reaches a required decision.
        """
        if target_step_number < 1:
            raise WorkflowStateService._conflict("The target step number must be positive.")

        session_data = WorkflowSessionRepository.get_by_id(session_id)
        if not session_data:
            raise WorkflowStateService._not_found(session_id)
        if session_data["status"] != "active":
            raise WorkflowStateService._conflict(
                "Only an active workflow session can record completed steps."
            )
        target_step = OWDRepository.get_step_by_ordinal(
            session_data["workflow_version_id"], target_step_number
        )
        if not target_step:
            raise WorkflowStateService._conflict(
                f"Step {target_step_number} does not exist in this published workflow."
            )

        session = WorkflowSession(**session_data)
        completed_step_numbers: List[int] = []
        for _ in range(100):
            position = WorkflowStateService.get_position(session)
            if session.status != "active":
                return WorkflowCompletionResult(session, completed_step_numbers)
            if not position.step_id:
                return WorkflowCompletionResult(
                    session,
                    completed_step_numbers,
                    stopped_at_decision=bool(position.decision_options),
                )
            current_number = int(position.step_number or 0)
            if current_number > target_step_number:
                return WorkflowCompletionResult(session, completed_step_numbers)

            session = WorkflowStateService.mark_step_complete(
                session_id,
                {
                    "completion_attestation": "completed_through_step",
                    "completion_target_step": target_step_number,
                },
            )
            completed_step_numbers.append(current_number)
            if current_number == target_step_number:
                return WorkflowCompletionResult(session, completed_step_numbers)

        raise WorkflowStateService._conflict(
            "The requested completion range is too large to process safely."
        )

    @staticmethod
    def advance_session(session_id: str, transition_context: Dict[str, Any]) -> WorkflowSession:
        """Advance a decision/rule state that has no remaining atomic step."""
        session_data = WorkflowSessionRepository.get_by_id(session_id)
        if not session_data:
            raise WorkflowStateService._not_found(session_id)
        if session_data["status"] != "active":
            raise WorkflowStateService._conflict("Only an active workflow session can advance.")
        current_state_id = session_data["current_state_id"]
        if OWDRepository.get_next_pending_step(session_id, current_state_id):
            raise WorkflowStateService._conflict(
                "Complete the current workflow step before selecting a transition."
            )
        state = OWDRepository.get_state_by_id(current_state_id)
        if not state:
            raise WorkMateException(message=f"Workflow state '{current_state_id}' was not found.")
        context = {**session_data.get("session_context", {}), **transition_context}
        transition = OWDRepository.get_next_state_transition(current_state_id, context)
        if not transition:
            if not bool(state.get("is_terminal")):
                raise WorkflowStateService._conflict(
                    "No workflow transition matches the supplied decision or rule results."
                )
            next_state_id = current_state_id
            new_status = "completed"
        else:
            next_state_id = transition["to_state_id"]
            new_status = WorkflowStateService._status_after_transition(transition)

        WorkflowSessionRepository.apply_progress(
            session_id=session_id,
            expected_state_id=current_state_id,
            expected_updated_at=session_data["updated_at"],
            session_context=context,
            next_state_id=next_state_id,
            new_status=new_status,
        )
        OWDRepository.record_analytics_event(
            session_id=session_id,
            workflow_version_id=session_data["workflow_version_id"],
            event_type="SESSION_COMPLETED" if new_status == "completed" else "STATE_ENTERED",
            state_id=next_state_id,
            payload=context,
        )
        return WorkflowStateService._reload(session_id)

    @staticmethod
    def advance_if_transition_matches(
        session_id: str, transition_context: Dict[str, Any]
    ) -> WorkflowSession:
        """Apply a conversational decision only when it exactly matches a graph edge."""
        session_data = WorkflowSessionRepository.get_by_id(session_id)
        if not session_data:
            raise WorkflowStateService._not_found(session_id)
        if session_data["status"] != "active":
            return WorkflowSession(**session_data)
        current_state_id = session_data["current_state_id"]
        if OWDRepository.get_next_pending_step(session_id, current_state_id):
            return WorkflowSession(**session_data)
        context = {**session_data.get("session_context", {}), **transition_context}
        if not OWDRepository.get_next_state_transition(current_state_id, context):
            return WorkflowSession(**session_data)
        return WorkflowStateService.advance_session(session_id, transition_context)

    @staticmethod
    def pause_session(session_id: str) -> WorkflowSession:
        return WorkflowStateService._change_status(session_id, "active", "paused")

    @staticmethod
    def resume_session(session_id: str) -> WorkflowSession:
        return WorkflowStateService._change_status(session_id, "paused", "active")

    @staticmethod
    def abandon_session(session_id: str, reason: str) -> WorkflowSession:
        session_data = WorkflowSessionRepository.get_by_id(session_id)
        if not session_data:
            raise WorkflowStateService._not_found(session_id)
        if session_data["status"] not in {"active", "paused"}:
            raise WorkflowStateService._conflict(
                "Only an active or paused workflow session can be abandoned."
            )
        context = {**session_data.get("session_context", {}), "abandon_reason": reason}
        changed = WorkflowSessionRepository.update_status(
            session_id, session_data["status"], "abandoned", context
        )
        if not changed:
            raise WorkflowStateService._conflict("The workflow session changed concurrently.")
        OWDRepository.record_analytics_event(
            session_id=session_id,
            workflow_version_id=session_data["workflow_version_id"],
            event_type="SESSION_ABANDONED",
            state_id=session_data["current_state_id"],
            payload={"reason": reason},
        )
        return WorkflowStateService._reload(session_id)

    @staticmethod
    def _change_status(session_id: str, expected: str, target: str) -> WorkflowSession:
        session_data = WorkflowSessionRepository.get_by_id(session_id)
        if not session_data:
            raise WorkflowStateService._not_found(session_id)
        if session_data["status"] != expected:
            raise WorkflowStateService._conflict(
                f"A {session_data['status']} workflow session cannot be changed to {target}."
            )
        changed = WorkflowSessionRepository.update_status(
            session_id, expected, target, session_data.get("session_context", {})
        )
        if not changed:
            raise WorkflowStateService._conflict("The workflow session changed concurrently.")
        return WorkflowStateService._reload(session_id)

    @staticmethod
    def _reload(session_id: str) -> WorkflowSession:
        session = WorkflowSessionRepository.get_by_id(session_id)
        if not session:
            raise WorkMateException(message=f"Failed to reload workflow session '{session_id}'.")
        return WorkflowSession(**session)
