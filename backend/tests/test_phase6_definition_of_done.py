"""Phase 6 Definition of Done (DoD) verification tests for Workflow State Engine."""

import pytest
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.copilot_session import router as session_router
from app.core.security import create_access_token
from app.services.workflow_state import WorkflowStateService
from app.models.workflow_session import WorkflowSession

app = FastAPI()
app.include_router(session_router, prefix="/api/v1")

client = TestClient(app)

EMP_TOKEN = create_access_token(user_id="usr_emp001", role="employee", department_id="dept_eng")

SOP_3_STEPS = {
    "id": "sop_valve_maintenance",
    "title": "Main Pressure Valve Maintenance SOP",
    "steps": [
        {"step_number": 0, "title": "Initial Inspection", "description": "Verify gauge pressure is zero."},
        {"step_number": 1, "title": "Valve Lockout", "description": "Apply lockout tag to Valve A."},
        {"step_number": 2, "title": "Housing Replacement", "description": "Replace housing gasket."},
    ],
}


# 1. Starting a session creates a workflow_sessions row at step 0
@patch("app.repositories.workflow_session_repository.WorkflowSessionRepository.create")
@patch("app.repositories.workflow_session_repository.WorkflowSessionRepository.get_by_id")
def test_dod_1_start_session_creates_row_at_step_0(mock_get_by_id, mock_create):
    mock_create.return_value = "sess_dod6_001"
    mock_get_by_id.return_value = {
        "id": "sess_dod6_001",
        "conversation_id": "conv_dod6_001",
        "workflow_version_id": "wv_sop_001",
        "current_step": 0,
        "status": "active",
        "created_at": "2026-08-04T00:00:00",
        "updated_at": "2026-08-04T00:00:00",
    }

    session = WorkflowStateService.start_session("conv_dod6_001", "wv_sop_001")
    assert session.id == "sess_dod6_001"
    assert session.current_step == 0
    assert session.status == "active"


# 2. Marking a step complete advances current_step and matches the SOP's actual next step
@patch("app.repositories.workflow_session_repository.WorkflowSessionRepository.get_by_id")
@patch("app.repositories.workflow_session_repository.WorkflowSessionRepository.update_step_and_status")
def test_dod_2_mark_step_complete_advances_and_matches_sop_next_step(mock_update, mock_get_by_id):
    mock_get_by_id.side_effect = [
        {"id": "sess_dod6_001", "conversation_id": "c", "workflow_version_id": "v", "current_step": 0, "status": "active", "created_at": "2026-08-04T00:00:00", "updated_at": "2026-08-04T00:00:00"},
        {"id": "sess_dod6_001", "conversation_id": "c", "workflow_version_id": "v", "current_step": 1, "status": "active", "created_at": "2026-08-04T00:00:00", "updated_at": "2026-08-04T00:00:00"},
        {"id": "sess_dod6_001", "conversation_id": "c", "workflow_version_id": "v", "current_step": 1, "status": "active", "created_at": "2026-08-04T00:00:00", "updated_at": "2026-08-04T00:00:00"},
    ]

    session = WorkflowStateService.mark_step_complete("sess_dod6_001", total_steps=3)
    assert session.current_step == 1

    # Verify get_next_action matches SOP's actual step 1 ("Valve Lockout")
    next_action = WorkflowStateService.get_next_action("sess_dod6_001", SOP_3_STEPS)
    assert next_action["step_number"] == 1
    assert next_action["step_data"]["title"] == "Valve Lockout"


# 3. Pausing and resuming a session preserves current_step correctly
@patch("app.repositories.workflow_session_repository.WorkflowSessionRepository.get_by_id")
@patch("app.repositories.workflow_session_repository.WorkflowSessionRepository.update_status")
def test_dod_3_pausing_and_resuming_preserves_current_step(mock_update_status, mock_get_by_id):
    # Step 1: Pause session at step 1
    mock_get_by_id.return_value = {
        "id": "sess_dod6_001",
        "conversation_id": "conv_dod6_001",
        "workflow_version_id": "wv_sop_001",
        "current_step": 1,
        "status": "paused",
        "created_at": "2026-08-04T00:00:00",
        "updated_at": "2026-08-04T00:00:00",
    }

    paused_session = WorkflowStateService.pause_session("sess_dod6_001")
    assert paused_session.current_step == 1

    # Step 2: Resume session via HTTP endpoint
    mock_get_by_id.return_value = {
        "id": "sess_dod6_001",
        "conversation_id": "conv_dod6_001",
        "workflow_version_id": "wv_sop_001",
        "current_step": 1,
        "status": "active",
        "created_at": "2026-08-04T00:00:00",
        "updated_at": "2026-08-04T00:00:00",
    }

    res = client.post(
        "/api/v1/copilot/session/sess_dod6_001/resume",
        headers={"Authorization": f"Bearer {EMP_TOKEN}"},
    )
    assert res.status_code == 200
    resumed_data = res.json()
    assert resumed_data["current_step"] == 1
    assert resumed_data["status"] == "active"


# 4. Out-of-range step count tampering handles gracefully (returns workflow_complete, not Error 500)
@patch("app.repositories.workflow_session_repository.WorkflowSessionRepository.get_by_id")
def test_dod_4_out_of_range_step_count_handled_gracefully(mock_get_by_id):
    # Simulate current_step tampered to 999 (far beyond SOP's 3 steps)
    mock_get_by_id.return_value = {
        "id": "sess_dod6_001",
        "current_step": 999,
        "status": "active",
    }

    # Must NOT raise exception or Error 500
    next_action = WorkflowStateService.get_next_action("sess_dod6_001", SOP_3_STEPS)
    assert next_action["action"] == "workflow_complete"
    assert next_action["step_number"] is None
    assert next_action["requires_action"] is False
    assert next_action["total_steps"] == 3
