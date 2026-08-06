"""Unit tests for WorkflowStateService and copilot session state routes."""

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

DUMMY_SOP = {
    "id": "sop_valve_101",
    "title": "Safety Valve SOP",
    "steps": [
        {"step_number": 0, "title": "Inspection", "requires_explanation": False, "requires_document": False},
        {"step_number": 1, "title": "Valve Shutdown", "requires_explanation": True, "requires_document": False},
        {"step_number": 2, "title": "Pressure Test", "requires_explanation": False, "requires_document": True},
    ],
}


@patch("app.repositories.workflow_session_repository.WorkflowSessionRepository.get_active_by_conversation")
def test_get_active_session(mock_get):
    mock_get.return_value = {
        "id": "sess_100",
        "conversation_id": "conv_1",
        "workflow_version_id": "ver_1",
        "knowledge_version_id": "ver_1",
        "current_step": 0,
        "status": "active",
        "abandon_reason": None,
        "created_at": "2026-08-04T00:00:00",
        "updated_at": "2026-08-04T00:00:00",
    }

    session = WorkflowStateService.get_active_session("conv_1")
    assert session is not None
    assert session.id == "sess_100"
    assert session.status == "active"


@patch("app.repositories.workflow_session_repository.WorkflowSessionRepository.create")
@patch("app.repositories.workflow_session_repository.WorkflowSessionRepository.get_by_id")
def test_start_session(mock_get_by_id, mock_create):
    mock_create.return_value = "sess_101"
    mock_get_by_id.return_value = {
        "id": "sess_101",
        "conversation_id": "conv_2",
        "workflow_version_id": "ver_2",
        "knowledge_version_id": "ver_2",
        "current_step": 0,
        "status": "active",
        "created_at": "2026-08-04T00:00:00",
        "updated_at": "2026-08-04T00:00:00",
    }

    session = WorkflowStateService.start_session("conv_2", "ver_2")
    assert session.id == "sess_101"
    assert session.current_step == 0


@patch("app.repositories.workflow_session_repository.WorkflowSessionRepository.get_by_id")
@patch("app.repositories.workflow_session_repository.WorkflowSessionRepository.update_step_and_status")
def test_mark_step_complete(mock_update, mock_get_by_id):
    mock_get_by_id.side_effect = [
        {"id": "sess_101", "current_step": 0, "status": "active", "conversation_id": "c", "workflow_version_id": "v", "knowledge_version_id": "v", "created_at": "2026-08-04T00:00:00", "updated_at": "2026-08-04T00:00:00"},
        {"id": "sess_101", "current_step": 1, "status": "active", "conversation_id": "c", "workflow_version_id": "v", "knowledge_version_id": "v", "created_at": "2026-08-04T00:00:00", "updated_at": "2026-08-04T00:00:00"},
    ]

    session = WorkflowStateService.mark_step_complete("sess_101", total_steps=3)
    assert session.current_step == 1
    mock_update.assert_called_once_with("sess_101", 1, "active")


@patch("app.repositories.workflow_session_repository.WorkflowSessionRepository.get_by_id")

def test_deterministic_get_next_action(mock_get_by_id):
    # Test Step 0: proceed_to_step
    mock_get_by_id.return_value = {"id": "sess_101", "current_step": 0, "status": "active"}
    action0 = WorkflowStateService.get_next_action("sess_101", DUMMY_SOP)
    assert action0["action"] == "proceed_to_step"
    assert action0["step_number"] == 0

    # Test Step 1: needs_explanation
    mock_get_by_id.return_value = {"id": "sess_101", "current_step": 1, "status": "active"}
    action1 = WorkflowStateService.get_next_action("sess_101", DUMMY_SOP)
    assert action1["action"] == "needs_explanation"
    assert action1["step_number"] == 1

    # Test Step 2: needs_document
    mock_get_by_id.return_value = {"id": "sess_101", "current_step": 2, "status": "active"}
    action2 = WorkflowStateService.get_next_action("sess_101", DUMMY_SOP)
    assert action2["action"] == "needs_document"
    assert action2["step_number"] == 2

    # Test Step 3 (out of bounds): workflow_complete
    mock_get_by_id.return_value = {"id": "sess_101", "current_step": 3, "status": "active"}
    action3 = WorkflowStateService.get_next_action("sess_101", DUMMY_SOP)
    assert action3["action"] == "workflow_complete"
    assert action3["step_number"] is None


@patch("app.repositories.workflow_session_repository.WorkflowSessionRepository.get_by_id")
@patch("app.repositories.workflow_session_repository.WorkflowSessionRepository.update_status")
def test_resume_session_endpoint(mock_update_status, mock_get_by_id):
    mock_get_by_id.return_value = {
        "id": "sess_paused_01",
        "conversation_id": "conv_1",
        "knowledge_version_id": "ver_1",
        "current_step": 1,
        "status": "active",
        "created_at": "2026-08-04T00:00:00",
        "updated_at": "2026-08-04T00:00:00",
    }

    res = client.post(
        "/api/v1/copilot/session/sess_paused_01/resume",
        headers={"Authorization": f"Bearer {EMP_TOKEN}"},
    )

    assert res.status_code == 200
    data = res.json()
    assert data["id"] == "sess_paused_01"
    assert data["status"] == "active"
    mock_update_status.assert_called_once_with("sess_paused_01", "active")
