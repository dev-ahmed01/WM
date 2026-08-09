"""Workflow State Engine Service.

Provides deterministic state-machine graph tracking for OWD workflow execution,
state transitions, step completion, pause, resume, abandonment, and next-action evaluation.
"""

import logging
from typing import Optional, Dict, Any, List
from fastapi import HTTPException, status

from app.models.workflow_session import WorkflowSession
from app.repositories.workflow_session_repository import WorkflowSessionRepository
from app.repositories.owd_repository import OWDRepository
from app.exceptions import WorkMateException

workflow_logger = logging.getLogger("copilot_services")


class WorkflowStateService:
    """Deterministic state-machine engine tracking active OWD workflow state transitions in Snowflake."""

    @staticmethod
    def get_active_session(conversation_id: str) -> Optional[WorkflowSession]:
        """Fetches active workflow session for a conversation thread."""
        session_dict = WorkflowSessionRepository.get_active_by_conversation(conversation_id)
        if not session_dict:
            return None
        return WorkflowSession(**session_dict)

    @staticmethod
    def start_session(conversation_id: str, workflow_version_id: str) -> WorkflowSession:
        """Begins tracking a new OWD workflow session at the initial workflow state."""
        # Try to resolve initial state node from compiled OWD structures
        initial_state = OWDRepository.get_initial_state(workflow_version_id)
        if not initial_state:
            raise WorkMateException(
                message=f"Workflow version '{workflow_version_id}' has no initial state."
            )
        
        session_id = WorkflowSessionRepository.create(
            conversation_id=conversation_id,
            workflow_version_id=workflow_version_id,
            current_state_id=initial_state["id"],
        )
        session_dict = WorkflowSessionRepository.get_by_id(session_id)
        if not session_dict:
            raise WorkMateException(message=f"Failed to load newly created workflow session '{session_id}'")
        
        # Log telemetry event
        OWDRepository.record_analytics_event(
            session_id=session_id,
            workflow_version_id=workflow_version_id,
            event_type="SESSION_STARTED",
            state_id=initial_state["id"] if initial_state else None,
        )

        workflow_logger.info(f"[WORKFLOW START] Started session '{session_id}' for version '{workflow_version_id}'")
        return WorkflowSession(**session_dict)

    @staticmethod
    def mark_step_complete(session_id: str, total_steps: Optional[int] = None, current_state_id: Optional[str] = None) -> WorkflowSession:
        """Advances workflow session to the next graph state or next step index."""
        session_dict = WorkflowSessionRepository.get_by_id(session_id)
        if not session_dict:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"error_code": "NOT_FOUND", "message": f"Workflow session '{session_id}' not found.", "details": None},
            )

        current_step = session_dict.get("current_step", 0)
        version_id = session_dict.get("workflow_version_id", "")
        next_step = current_step + 1

        # Attempt graph transition evaluation if state_id is provided
        new_status = "active"
        if current_state_id:
            next_transition = OWDRepository.get_next_state_transition(current_state_id)
            if next_transition and next_transition.get("is_terminal"):
                new_status = "completed"

        if total_steps is not None and next_step >= total_steps:
            new_status = "completed"

        WorkflowSessionRepository.update_step_and_status(session_id, next_step, new_status)
        updated_dict = WorkflowSessionRepository.get_by_id(session_id)
        if not updated_dict:
            raise WorkMateException(message=f"Failed to reload workflow session '{session_id}' after step update")
        
        # Log telemetry event
        OWDRepository.record_analytics_event(
            session_id=session_id,
            workflow_version_id=version_id,
            event_type="SESSION_COMPLETED" if new_status == "completed" else "STEP_COMPLETED",
            step_id=str(next_step),
        )

        workflow_logger.info(f"[WORKFLOW STEP COMPLETE] Session '{session_id}' advanced to step {next_step} ({new_status})")
        return WorkflowSession(**updated_dict)

    @staticmethod
    def pause_session(session_id: str) -> WorkflowSession:
        """Sets workflow session status='paused' for resumable workflows."""
        session_dict = WorkflowSessionRepository.get_by_id(session_id)
        if not session_dict:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"error_code": "NOT_FOUND", "message": f"Workflow session '{session_id}' not found.", "details": None},
            )

        WorkflowSessionRepository.update_status(session_id, "paused")
        updated_dict = WorkflowSessionRepository.get_by_id(session_id)
        if not updated_dict:
            raise WorkMateException(message=f"Failed to reload workflow session '{session_id}' after pause")
        workflow_logger.info(f"[WORKFLOW PAUSE] Session '{session_id}' paused")
        return WorkflowSession(**updated_dict)

    @staticmethod
    def resume_session(session_id: str) -> WorkflowSession:
        """Sets workflow session status='active' again."""
        session_dict = WorkflowSessionRepository.get_by_id(session_id)
        if not session_dict:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"error_code": "NOT_FOUND", "message": f"Workflow session '{session_id}' not found.", "details": None},
            )

        WorkflowSessionRepository.update_status(session_id, "active")
        updated_dict = WorkflowSessionRepository.get_by_id(session_id)
        if not updated_dict:
            raise WorkMateException(message=f"Failed to reload workflow session '{session_id}' after resume")
        workflow_logger.info(f"[WORKFLOW RESUME] Session '{session_id}' resumed to active")
        return WorkflowSession(**updated_dict)

    @staticmethod
    def abandon_session(session_id: str, reason: str) -> WorkflowSession:
        """Sets workflow session status='abandoned' with reason."""
        session_dict = WorkflowSessionRepository.get_by_id(session_id)
        if not session_dict:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"error_code": "NOT_FOUND", "message": f"Workflow session '{session_id}' not found.", "details": None},
            )

        WorkflowSessionRepository.update_status(session_id, "abandoned", abandon_reason=reason)
        updated_dict = WorkflowSessionRepository.get_by_id(session_id)
        if not updated_dict:
            raise WorkMateException(message=f"Failed to reload workflow session '{session_id}' after abandon")
        
        OWDRepository.record_analytics_event(
            session_id=session_id,
            workflow_version_id=session_dict.get("workflow_version_id", ""),
            event_type="SESSION_ABANDONED",
            payload={"reason": reason},
        )

        workflow_logger.info(f"[WORKFLOW ABANDON] Session '{session_id}' abandoned: {reason}")
        return WorkflowSession(**updated_dict)

    @staticmethod
    def get_next_action(session_id: str, sop_structure: Dict[str, Any]) -> Dict[str, Any]:
        """Evaluates next action deterministically from OWD states/steps without invoking LLM."""
        session_dict = WorkflowSessionRepository.get_by_id(session_id)
        if not session_dict:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"error_code": "NOT_FOUND", "message": f"Workflow session '{session_id}' not found.", "details": None},
            )

        current_step = session_dict.get("current_step", 0)
        steps = sop_structure.get("steps", [])
        total_steps = len(steps)

        # Check bounds: Workflow completion check
        if current_step >= total_steps and total_steps > 0:
            return {
                "action": "workflow_complete",
                "step_number": None,
                "step_data": None,
                "requires_action": False,
                "total_steps": total_steps,
            }

        # Index strictly into actual retrieved SOP step list
        step_data = steps[current_step] if total_steps > current_step else {
            "instruction": "Proceed with operational step.",
            "step_code": f"STEP_{current_step}",
        }

        if step_data.get("requires_explanation"):
            action = "needs_explanation"
        elif step_data.get("requires_document") or step_data.get("expected_output_type") == "DOCUMENT_UPLOAD":
            action = "needs_document"
        else:
            action = "proceed_to_step"

        return {
            "action": action,
            "step_number": current_step,
            "step_data": step_data,
            "requires_action": action in {"needs_explanation", "needs_document"},
            "total_steps": max(total_steps, 1),
        }
