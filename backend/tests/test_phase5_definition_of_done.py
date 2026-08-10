"""Phase 5 Definition of Done (DoD) verification tests for Retrieval & Validation Layer."""

import pytest
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.copilot import router as copilot_router
from app.core.security import create_access_token
from app.services.retrieval import RetrievalService
from app.services.validation import ResponseValidationService, CANONICAL_FALLBACK
from app.integrations.ai_gateway import AIGateway
from app.integrations.ai_provider import GeneratedAnswer

app = FastAPI()
app.include_router(copilot_router, prefix="/api/v1")

client = TestClient(app)

EMP_ENG_TOKEN = create_access_token(user_id="usr_emp001", role="employee", department_id="dept_eng")


# 1. Asking about content from a published document returns an answer with at least one citation
@pytest.mark.asyncio
@patch.object(AIGateway, "detect_intent")
@patch.object(RetrievalService, "retrieve_chunks")
@patch.object(AIGateway, "generate_response")
@patch("app.services.workflow_state.WorkflowStateService.get_active_session")
@patch("app.repositories.conversation_repository.ConversationRepository.get_or_create_session")
@patch("app.repositories.conversation_repository.ConversationRepository.persist_message")
@patch("app.repositories.conversation_repository.ConversationRepository.load_history")
@patch("app.repositories.conversation_repository.ConversationRepository.get_history")
@patch("app.services.analytics_service.AnalyticsService.record_event")
def test_dod_1_published_document_query_returns_citations(
    mock_record_evt, mock_get_hist, mock_load_hist, mock_persist, mock_session, mock_get_active, mock_generate, mock_retrieve, mock_detect
):
    mock_session.return_value = "conv_dod5_001"
    mock_persist.return_value = "msg_dod5_001"
    mock_load_hist.return_value = []
    mock_get_hist.return_value = []
    mock_get_active.return_value = None
    mock_detect.return_value = {"needs_clarification": False}
    mock_retrieve.return_value = [
        {
            "chunk_id": "chk_safety_101",
            "document_id": "doc_sop_safety_101",
            "document_title": "Safety SOP Manual v2.0",
            "version_number": 2,
            "step_number": 1,
            "department_id": "dept_eng",
            "status": "PUBLISHED",
            "content": "Verify pressure release valves before servicing.",
            "score": 0.94,
        }
    ]
    mock_generate.return_value = GeneratedAnswer("Step 1: Verify pressure release valves before servicing.", ["chk_safety_101"], "test")

    res = client.post(
        "/api/v1/copilot/message",
        headers={"Authorization": f"Bearer {EMP_ENG_TOKEN}"},
        json={"message": "How do I inspect the safety valve?"},
    )

    assert res.status_code == 200
    data = res.json()
    assert len(data["citations"]) >= 1
    assert data["citations"][0]["document_id"] == "doc_sop_safety_101"
    assert data["citations"][0]["document_title"] == "Safety SOP Manual v2.0"
    assert data["citations"][0]["version_number"] == 2


# 2. Asking something with no matching published knowledge returns the explicit "no verified guidance" fallback
@pytest.mark.asyncio
@patch.object(AIGateway, "detect_intent")
@patch.object(RetrievalService, "retrieve_chunks")
@patch("app.services.workflow_state.WorkflowStateService.get_active_session")
@patch("app.repositories.conversation_repository.ConversationRepository.get_or_create_session")
@patch("app.repositories.conversation_repository.ConversationRepository.persist_message")
@patch("app.repositories.conversation_repository.ConversationRepository.load_history")
@patch("app.repositories.conversation_repository.ConversationRepository.get_history")
@patch("app.services.analytics_service.AnalyticsService.record_event")
@patch("app.services.escalation.EscalationService.escalate")
def test_dod_2_no_matching_knowledge_returns_explicit_fallback(
    mock_escalate, mock_record_evt, mock_get_hist, mock_load_hist, mock_persist, mock_session, mock_get_active, mock_retrieve, mock_detect
):
    mock_session.return_value = "conv_dod5_002"
    mock_persist.return_value = "msg_dod5_002"
    mock_load_hist.return_value = []
    mock_get_hist.return_value = []
    mock_get_active.return_value = None
    mock_detect.return_value = {"needs_clarification": False}
    mock_retrieve.return_value = []

    res = client.post(
        "/api/v1/copilot/message",
        headers={"Authorization": f"Bearer {EMP_ENG_TOKEN}"},
        json={"message": "What is the secret code for alien spaceship?"},
    )

    assert res.status_code == 200
    data = res.json()
    assert data["answer"] == CANONICAL_FALLBACK
    assert data["citations"] == []
    assert data["confidence_score"] == 0.0
    assert data["requires_escalation"] is True


# 3. conversation_messages rows are created with confidence_score populated
@pytest.mark.asyncio
@patch.object(AIGateway, "detect_intent")
@patch.object(RetrievalService, "retrieve_chunks")
@patch.object(AIGateway, "generate_response")
@patch("app.services.workflow_state.WorkflowStateService.get_active_session")
@patch("app.repositories.conversation_repository.ConversationRepository.get_or_create_session")
@patch("app.repositories.conversation_repository.ConversationRepository.persist_message")
@patch("app.repositories.conversation_repository.ConversationRepository.load_history")
@patch("app.repositories.conversation_repository.ConversationRepository.get_history")
@patch("app.services.analytics_service.AnalyticsService.record_event")
def test_dod_3_conversation_messages_persisted_with_confidence_score(
    mock_record_evt, mock_get_hist, mock_load_hist, mock_persist, mock_session, mock_get_active, mock_generate, mock_retrieve, mock_detect
):
    mock_session.return_value = "conv_dod5_003"
    mock_persist.return_value = "msg_dod5_003"
    mock_load_hist.return_value = []
    mock_get_hist.return_value = []
    mock_get_active.return_value = None
    mock_detect.return_value = {"needs_clarification": False}
    mock_retrieve.return_value = [
        {
            "chunk_id": "chk_eng_01",
            "document_id": "doc_eng_01",
            "document_title": "Engineering SOP",
            "version_number": 1,
            "step_number": 1,
            "department_id": "dept_eng",
            "status": "PUBLISHED",
            "content": "Turn main switch off.",
            "score": 0.88,
        }
    ]
    mock_generate.return_value = GeneratedAnswer("Turn off the main switch.", ["chk_eng_01"], "test")

    res = client.post(
        "/api/v1/copilot/message",
        headers={"Authorization": f"Bearer {EMP_ENG_TOKEN}"},
        json={"message": "How to turn off main switch?"},
    )

    assert res.status_code == 200
    assert res.json()["confidence_score"] == 0.88


# 4. A department-scoped query never returns chunks from another department
@pytest.mark.asyncio
@patch.object(AIGateway, "search")
async def test_dod_4_department_scoped_query_never_returns_other_department_chunks(mock_search):
    mock_search.return_value = [
        {"chunk_id": "chk_ops_01", "status": "PUBLISHED", "department_id": "dept_ops", "content": "Ops content"},
        {"chunk_id": "chk_eng_01", "status": "PUBLISHED", "department_id": "dept_eng", "content": "Eng content"},
    ]

    eng_chunks = await RetrievalService.retrieve_chunks(query="procedure", department_id="dept_eng")
    assert len(eng_chunks) == 1
    assert eng_chunks[0]["department_id"] == "dept_eng"
    assert all(c["department_id"] == "dept_eng" for c in eng_chunks)
