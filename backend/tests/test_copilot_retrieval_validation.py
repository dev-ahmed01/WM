"""Unit tests for Copilot standalone Q&A, RetrievalService, and ResponseValidationService."""

import pytest
from unittest.mock import patch, MagicMock
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.copilot import router as copilot_router
from app.core.security import create_access_token
from app.services.retrieval import RetrievalService
from app.services.validation import ResponseValidationService, CANONICAL_FALLBACK
from app.integrations.cortex_client import CortexClient

app = FastAPI()
app.include_router(copilot_router, prefix="/api/v1")

client = TestClient(app)

EMPLOYEE_TOKEN = create_access_token(user_id="usr_emp001", role="employee", department_id="dept_eng")


@pytest.mark.asyncio
@patch.object(CortexClient, "search")
async def test_retrieval_service_filters_published_and_department(mock_search):
    mock_search.return_value = [
        {"chunk_id": "c1", "status": "PUBLISHED", "department_id": "dept_eng", "content": "Valid chunk"},
        {"chunk_id": "c2", "status": "DRAFT", "department_id": "dept_eng", "content": "Draft chunk"},
        {"chunk_id": "c3", "status": "PUBLISHED", "department_id": "dept_hr", "content": "HR chunk"},
    ]

    chunks = await RetrievalService.retrieve_chunks("safety valve", department_id="dept_eng")
    assert len(chunks) == 1
    assert chunks[0]["chunk_id"] == "c1"


def test_validation_service_zero_chunks_fallback():
    validated, requires_escalation = ResponseValidationService.validate_response(
        raw_response="Some guess answer",
        retrieved_chunks=[],
        user_role="employee",
        user_department_id="dept_eng",
    )

    assert requires_escalation is True
    assert validated.answer == CANONICAL_FALLBACK
    assert validated.confidence_score == 0.0
    assert validated.citations == []


def test_validation_service_valid_grounding():
    chunks = [
        {
            "chunk_id": "chk_1",
            "document_id": "doc_1",
            "document_title": "Valve SOP",
            "version_number": 1,
            "step_number": 2,
            "department_id": "dept_eng",
            "status": "PUBLISHED",
            "content": "Close valve A before valve B.",
            "score": 0.95,
        }
    ]

    validated, requires_escalation = ResponseValidationService.validate_response(
        raw_response="Close valve A before valve B.",
        retrieved_chunks=chunks,
        user_role="employee",
        user_department_id="dept_eng",
    )

    assert requires_escalation is False
    assert validated.confidence_score == 0.95
    assert len(validated.citations) == 1
    assert validated.citations[0].document_title == "Valve SOP"


@patch.object(CortexClient, "detect_intent")
@patch.object(RetrievalService, "retrieve_chunks")
@patch.object(CortexClient, "generate_response")
@patch("app.services.workflow_state.WorkflowStateService.get_active_session")
@patch("app.repositories.conversation_repository.ConversationRepository.get_or_create_session")
@patch("app.repositories.conversation_repository.ConversationRepository.persist_message")
@patch("app.repositories.conversation_repository.ConversationRepository.get_history")
@patch("app.services.analytics_service.AnalyticsService.record_event")
def test_copilot_message_endpoint_standalone_turn(
    mock_record_event,
    mock_get_history,
    mock_persist,
    mock_session,
    mock_get_active,
    mock_generate,
    mock_retrieve,
    mock_detect_intent,
):
    mock_session.return_value = "conv_test_123"
    mock_persist.return_value = "msg_test_123"
    mock_get_history.return_value = []
    mock_get_active.return_value = None
    mock_detect_intent.return_value = {"needs_clarification": False, "intent": "general"}
    mock_retrieve.return_value = [
        {
            "chunk_id": "chk_1",
            "document_id": "doc_1",
            "document_title": "Valve SOP",
            "version_number": 1,
            "department_id": "dept_eng",
            "status": "PUBLISHED",
            "content": "Close valve A before B.",
            "score": 0.88,
        }
    ]
    mock_generate.return_value = "Close valve A before valve B."

    response = client.post(
        "/api/v1/copilot/message",
        headers={"Authorization": f"Bearer {EMPLOYEE_TOKEN}"},
        json={"message": "How do I turn off the safety valve?"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["conversation_id"] == "conv_test_123"
    assert data["requires_escalation"] is False
    assert data["confidence_score"] == 0.88
    assert len(data["citations"]) == 1
    assert data["citations"][0]["document_title"] == "Valve SOP"

