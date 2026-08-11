"""Focused Copilot orchestration, workflow linkage, and safe-fallback tests."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.copilot import _match_decision_option, router
from app.core.security import create_access_token
from app.integrations.ai_gateway import AIGateway
from app.integrations.ai_provider import GeneratedAnswer
from app.models.workflow_session import (
    WorkflowDecisionOption,
    WorkflowPosition,
    WorkflowSession,
)
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


def test_natural_damage_language_uniquely_matches_persisted_decision_option():
    options = [
        WorkflowDecisionOption(
            option_code="OPT_DAMAGED", option_label="Yes, damaged cartons detected"
        ),
        WorkflowDecisionOption(
            option_code="OPT_INTACT", option_label="No, all cartons intact"
        ),
    ]

    assert _match_decision_option("the package is damaged", options) == "OPT_DAMAGED"
    assert _match_decision_option("package is intact", options) == "OPT_INTACT"
    assert _match_decision_option("cartons", options) is None


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
    # Intent classification is advisory. Verified evidence must still start the
    # workflow when a realistic paraphrase lacks an exact command keyword.
    mock_intent.return_value = {"intent": "GENERAL_QUERY", "needs_clarification": False}
    mock_retrieve.return_value = [
        source_chunk(
            chunk_id="chunk_2",
            state_id="state_2",
            step_number=2,
            step_title="Record the shipment temperature",
            content="Record the shipment temperature.",
        ),
        source_chunk(score=0.10),
    ]
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
        json={"message": "Inbound trailer at dock, seal needs checking"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["active_session_id"] == "sess_1"
    assert body["active_step_title"] == "Inspect the shipment seal"
    assert body["answer"].startswith("Current step: Inspect the shipment seal")
    assert 'type "done"' in body["answer"]
    assert body["citations"][0]["chunk_id"] == "chunk_1"
    mock_generate.assert_not_awaited()
    mock_start.assert_called_once_with(
        conversation_id="conv_1", workflow_version_id="ver_1", user_id="usr_emp"
    )


def test_done_completes_active_step_without_ai_or_retrieval():
    current = workflow_session()
    advanced = workflow_session().model_copy(update={"current_state_id": "state_2"})
    current_position = WorkflowPosition(
        state_id="state_1",
        state_title="Arrival inspection",
        state_type="ATOMIC_STEP",
        step_id="step_1",
        step_number=1,
        step_title="Inspect the shipment seal",
    )
    next_position = WorkflowPosition(
        state_id="state_2",
        state_title="Temperature check",
        state_type="ATOMIC_STEP",
        step_id="step_2",
        step_number=2,
        step_title="Record the shipment temperature",
    )

    with (
        patch(
            "app.api.v1.copilot.ConversationRepository.get_or_create_session",
            return_value="conv_1",
        ),
        patch(
            "app.api.v1.copilot.ConversationRepository.persist_message",
            side_effect=["user_msg", "ai_msg"],
        ),
        patch("app.api.v1.copilot.ConversationRepository.get_history", return_value=[]),
        patch(
            "app.api.v1.copilot.ConversationRepository.update_message_intent"
        ) as update_intent,
        patch(
            "app.api.v1.copilot.WorkflowStateService.get_current_session",
            return_value=current,
        ),
        patch(
            "app.api.v1.copilot.WorkflowStateService.get_position",
            side_effect=[current_position, next_position],
        ),
        patch(
            "app.api.v1.copilot.WorkflowStateService.mark_step_complete",
            return_value=advanced,
        ) as mark_complete,
        patch("app.api.v1.copilot.AnalyticsService.record_event"),
        patch.object(AIGateway, "detect_intent", new_callable=AsyncMock) as detect_intent,
        patch.object(AIGateway, "generate_response", new_callable=AsyncMock) as generate,
        patch.object(RetrievalService, "retrieve_chunks", new_callable=AsyncMock) as retrieve,
    ):
        response = client.post(
            "/api/v1/copilot/message",
            headers={"Authorization": f"Bearer {TOKEN}"},
            json={"conversation_id": "conv_1", "message": "done"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["answer"].startswith("Step completed. Next step:")
    assert body["active_step_number"] == 2
    assert body["active_step_title"] == "Record the shipment temperature"
    assert body["requires_escalation"] is False
    update_intent.assert_called_once_with("user_msg", "WORKFLOW_STEP_COMPLETE")
    mark_complete.assert_called_once_with("sess_1")
    detect_intent.assert_not_awaited()
    retrieve.assert_not_awaited()
    generate.assert_not_awaited()


def test_future_damage_question_is_acknowledged_without_skipping_current_step():
    current = workflow_session()
    current_position = WorkflowPosition(
        state_id="state_1",
        state_title="Arrival inspection",
        state_type="ATOMIC_STEP",
        step_id="step_1",
        step_number=1,
        step_title="Verify physical trailer door seal number against Bill of Lading manifest.",
    )
    future = source_chunk(
        chunk_id="chunk_damage",
        state_id="state_3",
        step_number=3,
        step_title="Container Damage Evaluation",
        content="State: Container Damage Evaluation (STATE_DECISION_DAMAGE)",
        score=1.0,
    )
    current_source = source_chunk(
        content=(
            "State: Dock Arrival and Seal Inspection. Instructions: Verify physical "
            "trailer door seal number against Bill of Lading manifest."
        ),
        score=1.0,
    )

    with (
        patch(
            "app.api.v1.copilot.ConversationRepository.get_or_create_session",
            return_value="conv_1",
        ),
        patch(
            "app.api.v1.copilot.ConversationRepository.persist_message",
            side_effect=["user_msg", "ai_msg"],
        ),
        patch("app.api.v1.copilot.ConversationRepository.get_history", return_value=[]),
        patch("app.api.v1.copilot.ConversationRepository.update_message_intent"),
        patch(
            "app.api.v1.copilot.WorkflowStateService.get_current_session",
            return_value=current,
        ),
        patch(
            "app.api.v1.copilot.WorkflowStateService.get_position",
            return_value=current_position,
        ),
        patch(
            "app.api.v1.copilot.WorkflowStateService.advance_if_transition_matches",
            return_value=current,
        ),
        patch("app.api.v1.copilot.AnalyticsService.record_event"),
        patch.object(
            AIGateway,
            "detect_intent",
            new_callable=AsyncMock,
            return_value={"intent": "GENERAL_QUERY", "needs_clarification": False},
        ),
        patch.object(
            RetrievalService,
            "retrieve_chunks",
            new_callable=AsyncMock,
            return_value=[future],
        ),
        patch.object(
            AIGateway,
            "get_workflow_state_source",
            new_callable=AsyncMock,
            return_value=current_source,
        ),
        patch.object(AIGateway, "generate_response", new_callable=AsyncMock) as generate,
    ):
        response = client.post(
            "/api/v1/copilot/message",
            headers={"Authorization": f"Bearer {TOKEN}"},
            json={
                "conversation_id": "conv_1",
                "message": "the package is damaged what should I do next",
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["is_grounded"] is True
    assert body["requires_escalation"] is False
    assert "Container Damage Evaluation is handled at workflow step 3" in body["answer"]
    assert "Do not skip ahead" in body["answer"]
    assert "Current step: Verify physical trailer door seal" in body["answer"]
    assert body["active_step_number"] == 1
    generate.assert_not_awaited()


def test_contextual_why_uses_active_rule_without_broad_retrieval():
    current = workflow_session()
    current_position = WorkflowPosition(
        state_id="state_1",
        state_title="Dock Arrival and Seal Inspection",
        state_type="ATOMIC_STEP",
        step_id="step_1",
        step_number=1,
        step_title="Verify physical trailer door seal number against Bill of Lading manifest.",
    )
    current_source = source_chunk(
        content=(
            "State: Dock Arrival and Seal Inspection | Instructions: STEP_CHECK_SEAL "
            "Verify physical trailer door seal number against Bill of Lading manifest. | "
            "Rules: RULE_SEAL_HARD_STOP Broken seal or tag mismatch requires immediate "
            "driver hold and QA escalation. | Keywords: SEAL, MISMATCH"
        ),
        score=1.0,
    )

    with (
        patch(
            "app.api.v1.copilot.ConversationRepository.get_or_create_session",
            return_value="conv_1",
        ),
        patch(
            "app.api.v1.copilot.ConversationRepository.persist_message",
            side_effect=["user_msg", "ai_msg"],
        ),
        patch(
            "app.api.v1.copilot.ConversationRepository.get_history",
            return_value=[
                {
                    "id": "previous_user",
                    "sender": "employee",
                    "content": "What if the seal number does not match?",
                }
            ],
        ),
        patch("app.api.v1.copilot.ConversationRepository.update_message_intent"),
        patch(
            "app.api.v1.copilot.WorkflowStateService.get_current_session",
            return_value=current,
        ),
        patch(
            "app.api.v1.copilot.WorkflowStateService.get_position",
            return_value=current_position,
        ),
        patch("app.api.v1.copilot.AnalyticsService.record_event"),
        patch.object(
            AIGateway,
            "detect_intent",
            new_callable=AsyncMock,
            return_value={"intent": "CONTEXTUAL_FOLLOW_UP", "needs_clarification": False},
        ),
        patch.object(
            AIGateway,
            "get_workflow_state_source",
            new_callable=AsyncMock,
            return_value=current_source,
        ),
        patch.object(RetrievalService, "retrieve_chunks", new_callable=AsyncMock) as retrieve,
        patch.object(AIGateway, "generate_response", new_callable=AsyncMock) as generate,
    ):
        response = client.post(
            "/api/v1/copilot/message",
            headers={"Authorization": f"Bearer {TOKEN}"},
            json={"conversation_id": "conv_1", "message": "Why?"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["requires_escalation"] is False
    assert body["is_grounded"] is True
    assert body["answer"].startswith(
        "Broken seal or tag mismatch requires immediate driver hold and QA escalation."
    )
    retrieve.assert_not_awaited()
    generate.assert_not_awaited()


@patch("app.api.v1.copilot.EscalationService.escalate", new_callable=AsyncMock)
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
def test_weak_match_does_not_start_workflow(
    mock_intent,
    mock_retrieve,
    mock_generate,
    _mock_conversation,
    _mock_persist,
    _mock_update_intent,
    _mock_history,
    _mock_current,
    mock_start,
    _mock_position,
    _mock_analytics,
    _mock_escalate,
):
    mock_intent.return_value = {"intent": "SOP_GUIDANCE", "needs_clarification": False}
    mock_retrieve.return_value = [source_chunk(score=0.51)]
    mock_generate.return_value = GeneratedAnswer(
        "Inspect the shipment seal before unloading.", ["chunk_1"], "test"
    )

    response = client.post(
        "/api/v1/copilot/message",
        headers={"Authorization": f"Bearer {TOKEN}"},
        json={"message": "Explain quantum nebula payroll crystallography protocol ZXQ-947."},
    )

    assert response.status_code == 200
    assert response.json()["answer"] == CANONICAL_FALLBACK
    assert response.json()["requires_escalation"] is True
    assert response.json()["active_session_id"] is None
    mock_start.assert_not_called()
    mock_generate.assert_not_awaited()


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
