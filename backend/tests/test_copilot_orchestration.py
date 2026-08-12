"""Focused Copilot orchestration, workflow linkage, and safe-fallback tests."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.copilot import (
    _claimed_current_step,
    _claims_previous_steps_without_target,
    _completion_through_target,
    _is_step_completion_message,
    _match_decision_option,
    _requested_sop_index,
    _requested_step_jump,
    router,
)
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
from app.services.workflow_state import WorkflowCompletionResult


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


def test_workflow_navigation_phrases_are_parsed_without_model_inference():
    assert _requested_sop_index("give me SOP 1") == 1
    assert _requested_sop_index("show sop1") == 1
    assert _requested_step_jump("can we not skip to step 3") == 3
    assert _requested_step_jump("jump to step3") == 3
    assert _claimed_current_step("I'm stuck on step 15") == 15
    assert _claimed_current_step("I am currently working at step 12") == 12
    assert _claimed_current_step("skip to step 15") is None
    assert _completion_through_target("I completed through step 2") == 2
    assert _completion_through_target("complete up to step2") == 2
    assert _completion_through_target("can I complete through step 2?") is None
    assert _claims_previous_steps_without_target(
        "I have completed the previous steps; the package is damaged"
    )


def test_completion_intent_is_case_typo_and_negation_safe():
    for message in ("done", "DoNe", "dne", "don", "I am finised", "step completed"):
        assert _is_step_completion_message(message)
    for message in ("not done", "are we done", "should I complete it?", "one"):
        assert not _is_step_completion_message(message)


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


def test_complete_through_command_records_attestation_without_ai_or_retrieval():
    current = workflow_session()
    current_position = WorkflowPosition(
        state_id="state_1",
        state_title="Arrival inspection",
        state_type="ATOMIC_STEP",
        step_id="step_1",
        step_number=1,
        step_title="Inspect the shipment seal",
    )
    decision_position = WorkflowPosition(
        state_id="state_decision",
        state_title="Container damage evaluation",
        state_type="DECISION",
        step_title="Container damage evaluation",
        decision_options=[
            WorkflowDecisionOption(
                option_code="OPT_DAMAGED",
                option_label="Yes, damaged cartons detected",
            )
        ],
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
            "app.api.v1.copilot.ConversationRepository.update_message_intent"
        ) as update_intent,
        patch(
            "app.api.v1.copilot.WorkflowStateService.get_current_session",
            return_value=current,
        ),
        patch(
            "app.api.v1.copilot.WorkflowStateService.get_position",
            side_effect=[current_position, decision_position],
        ),
        patch(
            "app.api.v1.copilot.WorkflowStateService.complete_through_step",
            return_value=WorkflowCompletionResult(
                session=current, completed_step_numbers=[1, 2]
            ),
        ) as complete_through,
        patch.object(AIGateway, "detect_intent", new_callable=AsyncMock) as detect_intent,
        patch.object(AIGateway, "generate_response", new_callable=AsyncMock) as generate,
        patch.object(RetrievalService, "retrieve_chunks", new_callable=AsyncMock) as retrieve,
    ):
        response = client.post(
            "/api/v1/copilot/message",
            headers={"Authorization": f"Bearer {TOKEN}"},
            json={"conversation_id": "conv_1", "message": "complete through step 2"},
        )

    assert response.status_code == 200
    body = response.json()
    assert "steps 1 through 2" in body["answer"]
    assert body["active_decision_options"][0]["option_code"] == "OPT_DAMAGED"
    assert body["requires_escalation"] is False
    complete_through.assert_called_once_with("sess_1", 2)
    update_intent.assert_called_once_with("user_msg", "WORKFLOW_MULTI_STEP_COMPLETE")
    detect_intent.assert_not_awaited()
    retrieve.assert_not_awaited()
    generate.assert_not_awaited()


def test_reported_step_position_resumes_there_without_replaying_from_step_one():
    current = workflow_session()
    resumed = workflow_session().model_copy(update={"current_state_id": "state_15"})
    current_position = WorkflowPosition(
        state_id="state_1",
        state_title="Start",
        state_type="ATOMIC_STEP",
        step_id="step_1",
        step_number=1,
        step_title="First check",
    )
    reported_position = WorkflowPosition(
        state_id="state_15",
        state_title="Reported work area",
        state_type="ATOMIC_STEP",
        step_id="step_15",
        step_number=15,
        step_title="Resolve the reported equipment condition",
    )
    completion = WorkflowCompletionResult(
        session=resumed,
        completed_step_numbers=list(range(1, 15)),
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
        patch("app.api.v1.copilot.ConversationRepository.update_message_intent"),
        patch(
            "app.api.v1.copilot.WorkflowStateService.get_current_session",
            return_value=current,
        ),
        patch(
            "app.api.v1.copilot.WorkflowStateService.get_position",
            side_effect=[current_position, reported_position],
        ),
        patch(
            "app.api.v1.copilot.OWDRepository.get_step_by_ordinal",
            return_value={"id": "step_15", "ordinal_index": 15},
        ),
        patch(
            "app.api.v1.copilot.WorkflowStateService.complete_through_step",
            return_value=completion,
        ) as complete_through,
        patch.object(AIGateway, "detect_intent", new_callable=AsyncMock) as detect,
        patch.object(RetrievalService, "retrieve_chunks", new_callable=AsyncMock) as retrieve,
    ):
        response = client.post(
            "/api/v1/copilot/message",
            headers={"Authorization": f"Bearer {TOKEN}"},
            json={"conversation_id": "conv_1", "message": "I'm stuck on step 15"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["active_step_number"] == 15
    assert "Resuming at your reported position" in body["answer"]
    assert "Resolve the reported equipment condition" in body["answer"]
    complete_through.assert_called_once_with("sess_1", 14)
    detect.assert_not_awaited()
    retrieve.assert_not_awaited()


def test_numbered_sop_request_uses_published_department_catalog():
    with (
        patch(
            "app.api.v1.copilot.ConversationRepository.get_or_create_session",
            return_value="conv_1",
        ),
        patch(
            "app.api.v1.copilot.ConversationRepository.persist_message",
            side_effect=["user_msg", "ai_msg"],
        ),
        patch("app.api.v1.copilot.ConversationRepository.update_message_intent"),
        patch(
            "app.api.v1.copilot.WorkflowStateService.get_current_session",
            return_value=None,
        ),
        patch(
            "app.api.v1.copilot.KnowledgeRepository.list_published_catalog",
            return_value=[
                {
                    "title": "Receive shipment",
                    "workflow_code": "SOP_INB_101",
                    "description": "Inbound receiving and inspection.",
                    "workflow_version_id": "ver_1",
                }
            ],
        ) as list_items,
        patch.object(AIGateway, "detect_intent", new_callable=AsyncMock) as detect_intent,
        patch.object(RetrievalService, "retrieve_chunks", new_callable=AsyncMock) as retrieve,
    ):
        response = client.post(
            "/api/v1/copilot/message",
            headers={"Authorization": f"Bearer {TOKEN}"},
            json={"message": "give me SOP 1"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["answer"].startswith("Inbound receiving and inspection.")
    assert body["spoken_answer"] == body["answer"]
    assert "SOP_INB_101" not in body["spoken_answer"]
    assert body["sop_details"] == "SOP 1: Receive shipment | SOP_INB_101"
    assert body["requires_escalation"] is False
    list_items.assert_called_once_with("dept_ops")
    detect_intent.assert_not_awaited()
    retrieve.assert_not_awaited()


def test_named_sop_request_starts_catalog_workflow_without_embeddings():
    session = workflow_session()
    position = WorkflowPosition(
        state_id="state_1",
        state_title="Arrival inspection",
        state_type="ATOMIC_STEP",
        step_id="step_1",
        step_number=1,
        step_title="Inspect the shipment seal",
    )
    catalog = [
        {
            "workflow_id": "workflow_1",
            "workflow_code": "SOP_INB_101",
            "title": "receive_shipment_v1_1",
            "description": "Inbound receiving, seal verification, and inventory intake.",
            "workflow_version_id": "ver_1",
            "version_number": 4,
        }
    ]

    with (
        patch(
            "app.api.v1.copilot.ConversationRepository.get_or_create_session",
            return_value="conv_1",
        ),
        patch(
            "app.api.v1.copilot.ConversationRepository.persist_message",
            side_effect=["user_msg", "ai_msg"],
        ),
        patch("app.api.v1.copilot.ConversationRepository.update_message_intent"),
        patch(
            "app.api.v1.copilot.WorkflowStateService.get_current_session",
            return_value=None,
        ),
        patch(
            "app.api.v1.copilot.KnowledgeRepository.list_published_catalog",
            return_value=catalog,
        ),
        patch(
            "app.api.v1.copilot.WorkflowStateService.start_session",
            return_value=session,
        ) as start_session,
        patch(
            "app.api.v1.copilot.WorkflowStateService.get_position",
            return_value=position,
        ),
        patch.object(AIGateway, "detect_intent", new_callable=AsyncMock) as detect_intent,
        patch.object(RetrievalService, "retrieve_chunks", new_callable=AsyncMock) as retrieve,
    ):
        response = client.post(
            "/api/v1/copilot/message",
            headers={"Authorization": f"Bearer {TOKEN}"},
            json={"message": "get me receive shipment sop"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["answer"].startswith("Current step: Inspect the shipment seal")
    assert body["spoken_answer"] == body["answer"]
    assert "receive_shipment_v1_1" not in body["spoken_answer"]
    assert body["sop_details"] == "SOP: receive_shipment_v1_1 | SOP_INB_101"
    assert body["active_step_number"] == 1
    assert body["confidence_score"] == 1.0
    start_session.assert_called_once_with(
        conversation_id="conv_1", workflow_version_id="ver_1", user_id="usr_emp"
    )
    detect_intent.assert_not_awaited()
    retrieve.assert_not_awaited()


def test_all_steps_done_stops_at_persisted_decision_without_escalation():
    current = workflow_session()
    decision_position = WorkflowPosition(
        state_id="state_decision",
        state_title="Container damage evaluation",
        state_type="DECISION",
        step_title="Container damage evaluation",
        decision_options=[
            WorkflowDecisionOption(
                option_code="OPT_DAMAGED",
                option_label="Yes, damaged cartons detected",
            ),
            WorkflowDecisionOption(
                option_code="OPT_INTACT",
                option_label="No, all cartons intact",
            ),
        ],
    )
    completion = WorkflowCompletionResult(
        session=current,
        completed_step_numbers=[1, 2],
        stopped_at_decision=True,
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
        patch("app.api.v1.copilot.ConversationRepository.update_message_intent"),
        patch(
            "app.api.v1.copilot.WorkflowStateService.get_current_session",
            return_value=current,
        ),
        patch(
            "app.api.v1.copilot.WorkflowStateService.get_position",
            side_effect=[decision_position, decision_position],
        ),
        patch(
            "app.api.v1.copilot.OWDRepository.get_last_step_ordinal",
            return_value=6,
        ),
        patch(
            "app.api.v1.copilot.WorkflowStateService.complete_through_step",
            return_value=completion,
        ) as complete_through,
        patch.object(AIGateway, "detect_intent", new_callable=AsyncMock) as detect_intent,
        patch.object(RetrievalService, "retrieve_chunks", new_callable=AsyncMock) as retrieve,
    ):
        response = client.post(
            "/api/v1/copilot/message",
            headers={"Authorization": f"Bearer {TOKEN}"},
            json={"conversation_id": "conv_1", "message": "all the steps are done"},
        )

    assert response.status_code == 200
    body = response.json()
    assert "steps 1 through 2" in body["answer"]
    assert "verified outcome is required" in body["answer"]
    assert len(body["active_decision_options"]) == 2
    assert body["requires_escalation"] is False
    complete_through.assert_called_once_with("sess_1", 6)
    detect_intent.assert_not_awaited()
    retrieve.assert_not_awaited()


def test_ai_planner_resolves_elliptical_completion_and_prior_damage_outcome():
    current = workflow_session()
    decision_session = workflow_session().model_copy(
        update={"current_state_id": "state_decision"}
    )
    advanced = workflow_session().model_copy(update={"current_state_id": "state_damage"})
    current_position = WorkflowPosition(
        state_id="state_1",
        state_title="Arrival inspection",
        state_type="ATOMIC_STEP",
        step_id="step_1",
        step_number=1,
        step_title="Inspect the shipment seal",
    )
    decision_position = WorkflowPosition(
        state_id="state_decision",
        state_title="Container damage evaluation",
        state_type="DECISION",
        decision_options=[
            WorkflowDecisionOption(
                option_code="OPT_DAMAGED",
                option_label="Yes, damaged cartons detected",
            ),
            WorkflowDecisionOption(
                option_code="OPT_INTACT",
                option_label="No, all cartons intact",
            ),
        ],
    )
    damage_position = WorkflowPosition(
        state_id="state_damage",
        state_title="Damage quarantine",
        state_type="ATOMIC_STEP",
        step_id="step_3",
        step_number=3,
        step_title="Apply red quarantine tape and transport to Bay Q-1.",
    )
    completion = WorkflowCompletionResult(
        session=decision_session,
        completed_step_numbers=[1, 2],
        stopped_at_decision=True,
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
                    "id": "prior_user",
                    "sender": "employee",
                    "content": "packages damaged what should I do",
                },
                {
                    "id": "prior_ai",
                    "sender": "ai",
                    "content": "Damage evaluation is handled after the current checks.",
                },
            ],
        ),
        patch("app.api.v1.copilot.ConversationRepository.update_message_intent"),
        patch(
            "app.api.v1.copilot.WorkflowStateService.get_current_session",
            return_value=current,
        ),
        patch(
            "app.api.v1.copilot.WorkflowStateService.get_position",
            side_effect=[current_position, decision_position, damage_position],
        ),
        patch(
            "app.api.v1.copilot.OWDRepository.get_last_step_ordinal",
            return_value=6,
        ),
        patch(
            "app.api.v1.copilot.WorkflowStateService.complete_through_step",
            return_value=completion,
        ) as complete_through,
        patch(
            "app.api.v1.copilot.WorkflowStateService.advance_if_transition_matches",
            return_value=advanced,
        ) as advance,
        patch.object(
            AIGateway,
            "plan_workflow_action",
            new_callable=AsyncMock,
            return_value={
                "intent": "continue_prior_issue",
                "completion_scope": "all_available",
                "outcome_text": "packages damaged",
                "needs_clarification": False,
                "confidence": 0.91,
                "authoritative": False,
            },
        ) as plan,
        patch.object(AIGateway, "detect_intent", new_callable=AsyncMock) as detect,
        patch.object(RetrievalService, "retrieve_chunks", new_callable=AsyncMock) as retrieve,
    ):
        response = client.post(
            "/api/v1/copilot/message",
            headers={"Authorization": f"Bearer {TOKEN}"},
            json={
                "conversation_id": "conv_1",
                "message": "I have done all this tasks tell me what should I do about",
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert "steps 1 through 2" in body["answer"]
    assert "Outcome recorded: Yes, damaged cartons detected" in body["answer"]
    assert "Apply red quarantine tape" in body["answer"]
    assert body["active_step_number"] == 3
    assert body["requires_escalation"] is False
    complete_through.assert_called_once_with("sess_1", 6)
    advance.assert_called_once()
    assert advance.call_args.args[1]["decision_option"] == "OPT_DAMAGED"
    plan.assert_awaited_once()
    detect.assert_not_awaited()
    retrieve.assert_not_awaited()


def test_future_damage_question_returns_direct_verified_guidance_without_advancing():
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
        state_id="state_4",
        step_number=4,
        step_title="Quality Quarantine Hold",
        content=(
            "State: Quality Quarantine Hold | Instructions: STEP_APPLY_TAPE "
            "Apply physical red quarantine tape to damaged pallet and transport to Bay Q-1."
        ),
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
    assert body["answer"] == (
        "Apply physical red quarantine tape to damaged pallet and transport to Bay Q-1."
    )
    assert "Do not skip ahead" not in body["answer"]
    assert body["active_step_number"] == 1
    generate.assert_not_awaited()


def test_completed_future_action_answers_with_persisted_following_step_without_metadata():
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
        chunk_id="chunk_quarantine",
        state_id="state_4",
        step_number=4,
        step_title="Quality Quarantine Hold",
        content=(
            "State: Quality Quarantine Hold | Instructions: STEP_APPLY_TAPE "
            "Apply physical red quarantine tape to damaged pallet and transport to Bay Q-1."
        ),
        score=0.9,
    )
    current_source = source_chunk(score=0.2)
    next_source = source_chunk(
        chunk_id="chunk_end",
        state_id="state_end",
        step_number=6,
        step_title="Receiving Completed",
        content="Receiving Completed (STATE_END)",
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
        patch(
            "app.api.v1.copilot.OWDRepository.get_next_state_transition",
            return_value={"to_state_id": "state_end", "is_terminal": True},
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
            return_value=[future, current_source],
        ),
        patch.object(
            AIGateway,
            "get_workflow_state_source",
            new_callable=AsyncMock,
            return_value=next_source,
        ) as get_state_source,
        patch.object(AIGateway, "generate_response", new_callable=AsyncMock) as generate,
    ):
        response = client.post(
            "/api/v1/copilot/message",
            headers={"Authorization": f"Bearer {TOKEN}"},
            json={
                "conversation_id": "conv_1",
                "message": "I have transported the packages to bay q 1 what should I do next",
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == "Receiving is now completed."
    assert body["spoken_answer"] == body["answer"]
    assert "Title:" not in body["answer"]
    assert "Keywords:" not in body["answer"]
    assert body["active_step_number"] == 1
    assert "STATE_END" not in body["answer"]
    assert body["citations"][0]["chunk_id"] == "chunk_end"
    get_state_source.assert_awaited_once_with("dept_ops", "ver_1", "state_end")
    generate.assert_not_awaited()


def test_semantic_followup_uses_prior_verified_state_when_retrieval_is_unavailable():
    current = workflow_session()
    current_position = WorkflowPosition(
        state_id="state_1",
        state_title="Arrival inspection",
        state_type="ATOMIC_STEP",
        step_id="step_1",
        step_number=1,
        step_title="Verify the trailer seal against the manifest.",
    )
    prior_instruction = (
        "Apply physical red quarantine tape to damaged pallet and transport to Bay Q-1."
    )
    history = [
        {"id": "prior_user", "sender": "employee", "content": "package damaged"},
        {
            "id": "prior_ai",
            "sender": "ai",
            "content": prior_instruction,
            "retrieved_state_ids": ["state_4"],
            "citations": [{"state_id": "state_4"}],
        },
    ]
    terminal_source = source_chunk(
        chunk_id="chunk_end",
        state_id="state_end",
        step_number=6,
        step_title="Receiving Completed",
        content="Receiving Completed (STATE_END)",
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
        ) as persist_message,
        patch(
            "app.api.v1.copilot.ConversationRepository.get_history",
            return_value=history,
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
        patch(
            "app.api.v1.copilot.OWDRepository.get_next_state_transition",
            return_value={"to_state_id": "state_end", "is_terminal": True},
        ),
        patch.object(
            AIGateway,
            "classify_verified_instruction_followup",
            new_callable=AsyncMock,
            return_value={
                "relation": "completed",
                "asks_next": True,
                "confidence": 0.94,
                "authoritative": False,
            },
        ) as classify_followup,
        patch.object(
            AIGateway,
            "get_workflow_state_source",
            new_callable=AsyncMock,
            return_value=terminal_source,
        ),
        patch.object(
            RetrievalService, "retrieve_chunks", new_callable=AsyncMock
        ) as retrieve,
        patch.object(AIGateway, "detect_intent", new_callable=AsyncMock) as detect,
        patch.object(AIGateway, "generate_response", new_callable=AsyncMock) as generate,
    ):
        response = client.post(
            "/api/v1/copilot/message",
            headers={"Authorization": f"Bearer {TOKEN}"},
            json={
                "conversation_id": "conv_1",
                "message": "transported to BAY q1 whats the next step",
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == "Receiving is now completed."
    assert body["is_grounded"] is True
    assert body["requires_escalation"] is False
    assert body["active_step_number"] == 1
    assert body["citations"][0]["state_id"] == "state_end"
    classify_followup.assert_awaited_once_with(
        "transported to BAY q1 whats the next step", prior_instruction
    )
    retrieve.assert_not_awaited()
    detect.assert_not_awaited()
    generate.assert_not_awaited()
    assert persist_message.call_args_list[1].kwargs["retrieved_state_ids"] == [
        "state_end"
    ]


def test_contextual_done_completes_adjacent_verified_guidance_not_active_step():
    current = workflow_session()
    current_position = WorkflowPosition(
        state_id="state_1",
        state_title="Arrival inspection",
        state_type="ATOMIC_STEP",
        step_id="step_1",
        step_number=1,
        step_title="Verify the trailer seal against the manifest.",
    )
    prior_instruction = (
        "Apply physical red quarantine tape to damaged pallet and transport to Bay Q-1."
    )
    history = [
        {"id": "prior_user", "sender": "employee", "content": "packages damaged"},
        {
            "id": "prior_ai",
            "sender": "ai",
            "content": prior_instruction,
            "retrieved_state_ids": ["state_4"],
            "citations": [{"state_id": "state_4"}],
        },
    ]
    terminal_source = source_chunk(
        chunk_id="chunk_end",
        state_id="state_end",
        step_number=6,
        step_title="Receiving Completed",
        content="Receiving Completed (STATE_END)",
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
            return_value=history,
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
        patch(
            "app.api.v1.copilot.WorkflowStateService.mark_step_complete"
        ) as mark_current_step,
        patch(
            "app.api.v1.copilot.OWDRepository.get_next_state_transition",
            return_value={"to_state_id": "state_end", "is_terminal": True},
        ),
        patch.object(
            AIGateway,
            "get_workflow_state_source",
            new_callable=AsyncMock,
            return_value=terminal_source,
        ),
        patch.object(
            RetrievalService, "retrieve_chunks", new_callable=AsyncMock
        ) as retrieve,
    ):
        response = client.post(
            "/api/v1/copilot/message",
            headers={"Authorization": f"Bearer {TOKEN}"},
            json={"conversation_id": "conv_1", "message": "DoNe"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == "Receiving is now completed."
    assert body["active_step_number"] == 1
    assert body["citations"][0]["state_id"] == "state_end"
    mark_current_step.assert_not_called()
    retrieve.assert_not_awaited()


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
