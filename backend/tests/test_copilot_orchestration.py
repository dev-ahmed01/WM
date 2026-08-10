"""Focused Copilot orchestration, workflow linkage, and safe-fallback tests."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.copilot import router
from app.core.security import create_access_token
from app.integrations.ai_gateway import AIGateway
from app.integrations.ai_provider import GeneratedAnswer
from app.models.workflow_session import WorkflowPosition, WorkflowSession
from app.services.retrieval import RetrievalService
from app.services.validation import CANONICAL_FALLBACK


app = FastAPI()
app.include_router(router, prefix="/api/v1")
client = TestClient(app)
TOKEN = create_access_token("usr_emp", "employee", "dept_ops")


def workflow_session() -> WorkflowSession:
    now = datetime.now(timezone.utc)
    return WorkflowSession(
        id="sess_1",
        conversation_id="conv_1",
        workflow_version_id="ver_1",
        current_state_id="state_1",
        user_id="usr_emp",
        status="active",
        started_at=now,
        updated_at=now,
    )


def source_chunk(**overrides):
    chunk = {
        "chunk_id": "chunk_1",
        "document_id": "doc_1",
        "workflow_id": "workflow_1",
        "workflow_version_id": "ver_1",
        "document_title": "Receiving SOP",
        "version_number": 1,
        "state_id": "state_1",
        "step_number": 1,
        "step_title": "Inspect seal",
        "department_id": "dept_ops",
        "status": "published",
        "content": "Inspect the shipment seal before unloading.",
        "score": 0.92,
    }
    chunk.update(overrides)
    return chunk


@patch("app.api.v1.copilot.AnalyticsService.record_event")
@patch("app.api.v1.copilot.WorkflowStateService.get_position")
@patch("app.api.v1.copilot.WorkflowStateService.start_session")
@patch("app.api.v1.copilot.WorkflowStateService.get_current_session", return_value=None)
@patch("app.api.v1.copilot.ConversationRepository.get_history", return_value=[])
@patch("app.api.v1.copilot.ConversationRepository.update_message_intent")
@patch("app.api.v1.copilot.ConversationRepository.persist_message", side_effect=["user_msg", "ai_msg"])
@patch("app.api.v1.copilot.ConversationRepository.get_or_create_session", return_value="conv_1")
@patch.object(AIGateway, "generate_response", new_callable=AsyncMock)
@patch.object(RetrievalService, "retrieve_chunks", new_callable=AsyncMock)
@patch.object(AIGateway, "detect_intent", new_callable=AsyncMock)
def test_retrieval_starts_workflow_and_returns_real_position(
    mock_intent,
    mock_retrieve,
    mock_generate,
    _mock_conversation,
    _mock_persist,
    _mock_update_intent,
    _mock_history,
    _mock_current,
    mock_start,
    mock_position,
    _mock_analytics,
):
    session = workflow_session()
    mock_intent.return_value = {"intent": "SOP_GUIDANCE", "needs_clarification": False}
    mock_retrieve.return_value = [source_chunk()]
    mock_generate.return_value = GeneratedAnswer(
        "Inspect the shipment seal before unloading.", ["chunk_1"], "test"
    )
    mock_start.return_value = session
    mock_position.return_value = WorkflowPosition(
        state_id="state_1",
        state_title="Arrival inspection",
        state_type="ATOMIC_STEP",
        step_id="step_1",
        step_number=1,
        step_title="Inspect the shipment seal",
    )

    response = client.post(
        "/api/v1/copilot/message",
        headers={"Authorization": f"Bearer {TOKEN}"},
        json={"message": "How do I receive this shipment?"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["active_session_id"] == "sess_1"
    assert body["active_step_title"] == "Inspect the shipment seal"
    assert body["citations"][0]["chunk_id"] == "chunk_1"
    mock_start.assert_called_once_with(
        conversation_id="conv_1", workflow_version_id="ver_1", user_id="usr_emp"
    )


@patch("app.api.v1.copilot.AnalyticsService.record_event", side_effect=RuntimeError("offline"))
@patch("app.api.v1.copilot.EscalationService.escalate", new_callable=AsyncMock, side_effect=RuntimeError("offline"))
@patch("app.api.v1.copilot.WorkflowStateService.get_current_session", return_value=None)
@patch("app.api.v1.copilot.ConversationRepository.get_history", return_value=[])
@patch("app.api.v1.copilot.ConversationRepository.update_message_intent")
@patch("app.api.v1.copilot.ConversationRepository.persist_message", side_effect=["user_msg", "ai_msg"])
@patch("app.api.v1.copilot.ConversationRepository.get_or_create_session", return_value="conv_1")
@patch.object(
    AIGateway,
    "generate_response",
    new_callable=AsyncMock,
    return_value=GeneratedAnswer("No evidence", [], "test"),
)
@patch.object(RetrievalService, "retrieve_chunks", new_callable=AsyncMock, return_value=[])
@patch.object(AIGateway, "detect_intent", new_callable=AsyncMock)
def test_no_evidence_fails_closed_when_side_effects_are_offline(
    mock_intent, *_mocks
):
    mock_intent.return_value = {"intent": "GENERAL_QUERY", "needs_clarification": False}
    response = client.post(
        "/api/v1/copilot/message",
        headers={"Authorization": f"Bearer {TOKEN}"},
        json={"message": "Unknown procedure"},
    )
    assert response.status_code == 200
    assert response.json()["answer"] == CANONICAL_FALLBACK
    assert response.json()["requires_escalation"] is True
