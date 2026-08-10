"""Unit tests for full Copilot orchestration pipeline, escalation integration, and session endpoints."""

import pytest
from unittest.mock import patch, AsyncMock
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.copilot import router as copilot_router
from app.api.v1.copilot_session import router as session_router
from app.core.security import create_access_token
from app.models.workflow_session import WorkflowSession
from app.services.retrieval import RetrievalService
<<<<<<< HEAD
from app.integrations.ai_gateway import AIGateway
from app.integrations.ai_provider import GeneratedAnswer
=======
from app.integrations.cortex_client import CortexClient
>>>>>>> origin/main
from app.services.validation import CANONICAL_FALLBACK

app = FastAPI()
app.include_router(copilot_router, prefix="/api/v1")
app.include_router(session_router, prefix="/api/v1")

client = TestClient(app)

EMP_ENG_TOKEN = create_access_token(user_id="usr_emp001", role="employee", department_id="dept_eng")


@pytest.mark.asyncio
@patch.object(AIGateway, "detect_intent")
@patch.object(RetrievalService, "retrieve_chunks")
@patch.object(AIGateway, "generate_response")
@patch("app.repositories.conversation_repository.ConversationRepository.get_or_create_session")
@patch("app.repositories.conversation_repository.ConversationRepository.persist_message")
@patch("app.repositories.conversation_repository.ConversationRepository.load_history")
@patch("app.repositories.conversation_repository.ConversationRepository.get_history")
@patch("app.services.workflow_state.WorkflowStateService.get_active_session")
@patch("app.services.analytics_service.AnalyticsService.record_event")
def test_full_copilot_turn_success(
    mock_record_event,
    mock_get_active_session,
    mock_get_history,
    mock_load_history,
    mock_persist,
    mock_session,
    mock_generate,
    mock_retrieve,
    mock_detect_intent,
):
    mock_session.return_value = "conv_full_001"
    mock_persist.return_value = "msg_full_001"
    mock_load_history.return_value = []
    mock_get_history.return_value = []
    mock_detect_intent.return_value = {"needs_clarification": False, "intent": "procedure_query"}
    mock_get_active_session.return_value = None

    mock_retrieve.return_value = [
        {
            "chunk_id": "chk_eng_01",
            "document_id": "doc_eng_01",
            "document_title": "Valve Maintenance SOP",
            "version_number": 1,
            "step_number": 1,
            "department_id": "dept_eng",
            "status": "PUBLISHED",
            "content": "Step 1: Check valve pressure gauge.",
            "score": 0.92,
        }
    ]
    mock_generate.return_value = GeneratedAnswer("Check the valve pressure gauge before proceeding.", ["chk_eng_01"], "test")

    res = client.post(
        "/api/v1/copilot/message",
        headers={"Authorization": f"Bearer {EMP_ENG_TOKEN}"},
        json={"message": "How do I check valve pressure?"},
    )

    assert res.status_code == 200
    data = res.json()
    assert data["conversation_id"] == "conv_full_001"
    assert data["requires_escalation"] is False
    assert data["confidence_score"] == 0.80
    assert len(data["citations"]) == 1
    assert data["citations"][0]["document_title"] == "Valve Maintenance SOP"
    mock_record_event.assert_called()


@pytest.mark.asyncio
@patch.object(AIGateway, "detect_intent")
@patch("app.repositories.conversation_repository.ConversationRepository.get_or_create_session")
@patch("app.repositories.conversation_repository.ConversationRepository.persist_message")
@patch("app.repositories.conversation_repository.ConversationRepository.load_history")
@patch("app.repositories.conversation_repository.ConversationRepository.get_history")
def test_copilot_clarification_short_circuit(
    mock_get_history, mock_load_history, mock_persist, mock_session, mock_detect_intent
):
    mock_session.return_value = "conv_ambiguous_01"
    mock_persist.return_value = "msg_clarify_01"
    mock_load_history.return_value = []
    mock_get_history.return_value = []
    mock_detect_intent.return_value = {"needs_clarification": True, "reason": "Ambiguous SOP target"}

    res = client.post(
        "/api/v1/copilot/message",
        headers={"Authorization": f"Bearer {EMP_ENG_TOKEN}"},
        json={"message": "Do the thing"},
    )

    assert res.status_code == 200
    data = res.json()
    assert "specify which SOP" in data["answer"]
    assert data["confidence_score"] == 0.0
    assert data["is_grounded"] is False
    assert data["requires_escalation"] is False


<<<<<<< HEAD
@patch.object(AIGateway, "detect_intent", new_callable=AsyncMock)
@patch.object(RetrievalService, "retrieve_chunks", new_callable=AsyncMock)
@patch.object(AIGateway, "generate_response", new_callable=AsyncMock)
=======
@patch.object(CortexClient, "detect_intent", new_callable=AsyncMock)
@patch.object(RetrievalService, "retrieve_chunks", new_callable=AsyncMock)
@patch.object(CortexClient, "generate_response", new_callable=AsyncMock)
>>>>>>> origin/main
@patch("app.repositories.conversation_repository.ConversationRepository.get_or_create_session")
@patch("app.repositories.conversation_repository.ConversationRepository.persist_message")
@patch("app.repositories.conversation_repository.ConversationRepository.get_history")
@patch("app.services.workflow_state.WorkflowStateService.get_active_session")
@patch("app.api.v1.copilot.EscalationService.escalate", new_callable=AsyncMock)
@patch("app.api.v1.copilot.AnalyticsService.record_event")
def test_grounded_fallback_survives_escalation_and_analytics_failures(
    mock_record_event,
    mock_escalate,
    mock_get_active_session,
    mock_get_history,
    mock_persist,
    mock_session,
    mock_generate,
    mock_retrieve,
    mock_detect_intent,
):
    mock_session.return_value = "conv_fallback_001"
    mock_persist.return_value = "msg_fallback_001"
    mock_get_history.return_value = []
    mock_get_active_session.return_value = None
    mock_detect_intent.return_value = {"needs_clarification": False}
    mock_retrieve.return_value = []
<<<<<<< HEAD
    mock_generate.return_value = GeneratedAnswer("", [], "none")
=======
    mock_generate.return_value = "No knowledge found."
>>>>>>> origin/main
    mock_escalate.side_effect = RuntimeError("missing escalation grant")
    mock_record_event.side_effect = RuntimeError("analytics unavailable")

    response = client.post(
        "/api/v1/copilot/message",
        headers={"Authorization": f"Bearer {EMP_ENG_TOKEN}"},
        json={"message": "How do I perform an unknown procedure?"},
    )

    assert response.status_code == 200
    assert response.json()["answer"] == CANONICAL_FALLBACK
    assert response.json()["requires_escalation"] is True
    mock_escalate.assert_awaited_once()


@patch("app.repositories.workflow_session_repository.WorkflowSessionRepository.get_by_id")
def test_get_session_endpoint(mock_get_by_id):
    mock_get_by_id.return_value = {
        "id": "sess_get_001",
        "conversation_id": "conv_101",
        "knowledge_version_id": "ver_202",
        "current_step": 2,
        "status": "active",
        "abandon_reason": None,
        "created_at": "2026-08-04T00:00:00",
        "updated_at": "2026-08-04T00:00:00",
    }

    res = client.get(
        "/api/v1/copilot/session/sess_get_001",
        headers={"Authorization": f"Bearer {EMP_ENG_TOKEN}"},
    )

    assert res.status_code == 200
    data = res.json()
    assert data["id"] == "sess_get_001"
    assert data["current_step"] == 2
    assert data["status"] == "active"
