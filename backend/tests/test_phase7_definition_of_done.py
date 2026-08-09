"""Phase 7 Definition of Done (DoD) verification tests for Frontend-Backend Copilot Integration."""

import pytest
from unittest.mock import patch, AsyncMock
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.copilot import router as copilot_router
from app.core.security import create_access_token
from app.models.workflow_session import WorkflowSession
from app.services.retrieval import RetrievalService
from app.services.validation import CANONICAL_FALLBACK
from app.integrations.ai_gateway import AIGateway
from app.integrations.ai_provider import GeneratedAnswer

app = FastAPI()
app.include_router(copilot_router, prefix="/api/v1")

client = TestClient(app)

EMP_TOKEN = create_access_token(user_id="usr_emp001", role="employee", department_id="dept_eng")


# 1. Full round trip returns a grounded, cited response
@patch.object(AIGateway, "detect_intent", new_callable=AsyncMock)
@patch.object(RetrievalService, "retrieve_chunks", new_callable=AsyncMock)
@patch.object(AIGateway, "generate_response", new_callable=AsyncMock)
@patch("app.repositories.conversation_repository.ConversationRepository.get_or_create_session")
@patch("app.repositories.conversation_repository.ConversationRepository.persist_message")
@patch("app.repositories.conversation_repository.ConversationRepository.load_history")
@patch("app.repositories.conversation_repository.ConversationRepository.get_history")
@patch("app.services.workflow_state.WorkflowStateService.get_active_session")
def test_dod7_1_full_roundtrip_grounded_cited_response(
    mock_get_active, mock_get_hist, mock_load_hist, mock_persist, mock_session, mock_generate, mock_retrieve, mock_detect
):
    mock_session.return_value = "conv_phase7_01"
    mock_persist.return_value = "msg_phase7_01"
    mock_load_hist.return_value = []
    mock_get_hist.return_value = []
    mock_get_active.return_value = None
    mock_detect.return_value = {"needs_clarification": False}
    mock_retrieve.return_value = [
        {
            "chunk_id": "chk_eng_101",
            "document_id": "doc_eng_101",
            "document_title": "Emergency Valve Isolation SOP",
            "version_number": 2,
            "step_number": 1,
            "department_id": "dept_eng",
            "status": "PUBLISHED",
            "content": "Turn handwheel counterclockwise 5 full rotations.",
            "score": 0.95,
        }
    ]
    mock_generate.return_value = GeneratedAnswer("Turn the handwheel counterclockwise 5 full rotations.", ["chk_eng_101"], "test")

    res = client.post(
        "/api/v1/copilot/message",
        headers={"Authorization": f"Bearer {EMP_TOKEN}"},
        json={"message": "How do I isolate emergency valve?"},
    )

    assert res.status_code == 200
    data = res.json()
    assert data["is_grounded"] is True
    assert data["requires_escalation"] is False
    assert len(data["citations"]) == 1
    assert data["citations"][0]["document_title"] == "Emergency Valve Isolation SOP"
    assert data["citations"][0]["version_number"] == 2


# 2. Continuing an active workflow correctly shows SOP step indicator fields
@patch.object(AIGateway, "detect_intent", new_callable=AsyncMock)
@patch.object(RetrievalService, "retrieve_chunks", new_callable=AsyncMock)
@patch.object(AIGateway, "generate_response", new_callable=AsyncMock)
@patch("app.repositories.conversation_repository.ConversationRepository.get_or_create_session")
@patch("app.repositories.conversation_repository.ConversationRepository.persist_message")
@patch("app.repositories.conversation_repository.ConversationRepository.load_history")
@patch("app.repositories.conversation_repository.ConversationRepository.get_history")
@patch("app.services.workflow_state.WorkflowStateService.get_active_session")
@patch("app.services.workflow_state.WorkflowStateService.mark_step_complete")
def test_dod7_2_active_workflow_shows_sop_step_indicator(
    mock_mark_complete, mock_get_active, mock_get_hist, mock_load_hist, mock_persist, mock_session, mock_generate, mock_retrieve, mock_detect
):
    mock_session.return_value = "conv_phase7_02"
    mock_persist.return_value = "msg_phase7_02"
    mock_load_hist.return_value = []
    mock_get_hist.return_value = []
    mock_detect.return_value = {"needs_clarification": False}

    active_sess = WorkflowSession(
        id="sess_active_01",
        conversation_id="conv_phase7_02",
        workflow_version_id="ver_sop_valve_101",
        current_step=1,
        status="active",
        created_at="2026-08-04T00:00:00",
        updated_at="2026-08-04T00:00:00",
    )
    mock_get_active.return_value = active_sess
    mock_mark_complete.return_value = active_sess

    mock_retrieve.return_value = [
        {
            "chunk_id": "c1",
            "document_id": "d1",
            "document_title": "SOP Title",
            "version_number": 1,
            "step_number": 1,
            "department_id": "dept_eng",
            "status": "PUBLISHED",
            "content": "Step 1 content",
            "score": 0.90,
        }
    ]
    mock_generate.return_value = GeneratedAnswer("Step 1 content guidance.", ["c1"], "test")

    res = client.post(
        "/api/v1/copilot/message",
        headers={"Authorization": f"Bearer {EMP_TOKEN}"},
        json={"message": "What is the next step?"},
    )

    assert res.status_code == 200
    data = res.json()
    assert data["active_sop_id"] == "ver_sop_valve_101"
    assert data["active_step_number"] == 1
    assert "Step 1" in data["active_step_title"]


# 3. Deliberately vague message triggers clarifying question, not a guess
@patch.object(AIGateway, "detect_intent", new_callable=AsyncMock)
@patch("app.repositories.conversation_repository.ConversationRepository.get_or_create_session")
@patch("app.repositories.conversation_repository.ConversationRepository.persist_message")
@patch("app.repositories.conversation_repository.ConversationRepository.load_history")
@patch("app.repositories.conversation_repository.ConversationRepository.get_history")
@patch("app.services.workflow_state.WorkflowStateService.get_active_session")
def test_dod7_3_vague_message_triggers_clarifying_question(
    mock_get_active, mock_get_hist, mock_load_hist, mock_persist, mock_session, mock_detect
):
    mock_session.return_value = "conv_phase7_03"
    mock_persist.return_value = "msg_phase7_03"
    mock_load_hist.return_value = []
    mock_get_hist.return_value = []
    mock_get_active.return_value = None
    mock_detect.return_value = {"needs_clarification": True, "reason": "Vague instruction"}

    res = client.post(
        "/api/v1/copilot/message",
        headers={"Authorization": f"Bearer {EMP_TOKEN}"},
        json={"message": "please do it"},
    )

    assert res.status_code == 200
    data = res.json()
    assert "specify which SOP" in data["answer"]
    assert data["requires_escalation"] is False
    assert data["is_grounded"] is False


# 4. Forcing low-confidence case shows escalation banner and creates an escalations row
@patch.object(AIGateway, "detect_intent", new_callable=AsyncMock)
@patch.object(RetrievalService, "retrieve_chunks", new_callable=AsyncMock)
@patch.object(AIGateway, "generate_response", new_callable=AsyncMock)
@patch("app.repositories.conversation_repository.ConversationRepository.get_or_create_session")
@patch("app.repositories.conversation_repository.ConversationRepository.persist_message")
@patch("app.repositories.conversation_repository.ConversationRepository.load_history")
@patch("app.repositories.conversation_repository.ConversationRepository.get_history")
@patch("app.services.workflow_state.WorkflowStateService.get_active_session")
@patch("app.repositories.escalation_repository.EscalationRepository.create")
def test_dod7_4_low_confidence_forces_escalation_banner_and_creates_escalation_row(
    mock_create_esc, mock_get_active, mock_get_hist, mock_load_hist, mock_persist, mock_session, mock_generate, mock_retrieve, mock_detect
):
    mock_session.return_value = "conv_phase7_04"
    mock_persist.return_value = "msg_phase7_04"
    mock_load_hist.return_value = []
    mock_get_hist.return_value = []
    mock_get_active.return_value = None
    mock_detect.return_value = {"needs_clarification": False}
    mock_retrieve.return_value = []  # No published knowledge found
    mock_generate.return_value = GeneratedAnswer("", [], "none")
    mock_create_esc.return_value = "esc_phase7_001"

    res = client.post(
        "/api/v1/copilot/message",
        headers={"Authorization": f"Bearer {EMP_TOKEN}"},
        json={"message": "How do I build a time machine?"},
    )

    assert res.status_code == 200
    data = res.json()
    assert data["answer"] == CANONICAL_FALLBACK
    assert data["requires_escalation"] is True
    assert data["confidence_score"] == 0.0
    mock_create_esc.assert_called_once()
