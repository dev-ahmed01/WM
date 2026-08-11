"""Workflow engine tests against the migration-backed state cursor contract."""

from datetime import datetime, timezone
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.copilot_session import router
from app.core.security import create_access_token
from app.models.workflow_session import WorkflowPosition, WorkflowSession
from app.repositories.owd_repository import OWDRepository
from app.services.workflow_state import WorkflowStateService


def session_row(**overrides):
    now = datetime.now(timezone.utc)
    row = {
        "id": "sess_1",
        "conversation_id": "conv_1",
        "workflow_version_id": "ver_1",
        "current_state_id": "state_1",
        "previous_state_id": None,
        "user_id": "usr_owner",
        "status": "active",
        "session_context": {},
        "started_at": now,
        "updated_at": now,
        "completed_at": None,
    }
    row.update(overrides)
    return row


@patch("app.services.workflow_state.WorkflowSessionRepository.get_active_by_conversation")
def test_get_active_session_uses_state_schema(mock_get):
    mock_get.return_value = session_row()
    session = WorkflowStateService.get_active_session("conv_1")
    assert session.current_state_id == "state_1"
    assert session.status == "active"


@patch("app.services.workflow_state.OWDRepository.get_decision_options")
@patch("app.services.workflow_state.OWDRepository.get_next_pending_step", return_value=None)
@patch("app.services.workflow_state.OWDRepository.get_state_by_id")
def test_position_exposes_only_persisted_decision_options(mock_state, _mock_step, mock_options):
    mock_state.return_value = {
        "id": "state_1",
        "workflow_version_id": "ver_1",
        "title": "Inspect result",
        "state_type": "DECISION",
    }
    mock_options.return_value = [
        {"option_code": "OPT_ACCEPT", "option_label": "Accept shipment"}
    ]

    position = WorkflowStateService.get_position(WorkflowSession(**session_row()))

    assert position.decision_options[0].option_code == "OPT_ACCEPT"
    mock_options.assert_called_once_with("state_1")


@patch("app.services.workflow_state.OWDRepository.get_decision_options", return_value=[])
@patch("app.services.workflow_state.OWDRepository.get_next_pending_step")
@patch("app.services.workflow_state.OWDRepository.get_state_by_id")
def test_position_preserves_one_based_global_step_number(mock_state, mock_step, _mock_options):
    mock_state.return_value = {
        "id": "state_1",
        "workflow_version_id": "ver_1",
        "title": "Arrival inspection",
        "state_type": "ATOMIC_STEP",
    }
    mock_step.return_value = {
        "id": "step_1",
        "ordinal_index": 1,
        "instruction": "Inspect the seal",
        "expected_output_type": "confirmation",
    }

    position = WorkflowStateService.get_position(WorkflowSession(**session_row()))

    assert position.step_number == 1


@patch("app.services.workflow_state.OWDRepository.record_analytics_event")
@patch("app.services.workflow_state.WorkflowSessionRepository.get_by_id")
@patch("app.services.workflow_state.WorkflowSessionRepository.create")
@patch("app.services.workflow_state.OWDRepository.get_initial_state")
def test_start_session_persists_initial_state_and_user(mock_initial, mock_create, mock_get, mock_event):
    mock_initial.return_value = {"id": "state_initial"}
    mock_create.return_value = "sess_1"
    mock_get.return_value = session_row(current_state_id="state_initial")

    session = WorkflowStateService.start_session("conv_1", "ver_1", "usr_owner")

    assert session.current_state_id == "state_initial"
    mock_create.assert_called_once_with(
        conversation_id="conv_1",
        workflow_version_id="ver_1",
        current_state_id="state_initial",
        user_id="usr_owner",
        session_context={},
    )


@patch("app.services.workflow_state.OWDRepository.record_analytics_event")
@patch("app.services.workflow_state.WorkflowSessionRepository.apply_progress")
@patch("app.services.workflow_state.OWDRepository.count_pending_steps", return_value=2)
@patch("app.services.workflow_state.OWDRepository.get_next_pending_step")
@patch("app.services.workflow_state.OWDRepository.get_state_by_id")
@patch("app.services.workflow_state.WorkflowSessionRepository.get_by_id")
def test_step_completion_records_real_step_without_leaving_state(
    mock_get, mock_state, mock_step, _mock_count, mock_apply, _mock_event
):
    mock_get.side_effect = [session_row(), session_row()]
    mock_state.return_value = {"id": "state_1", "is_terminal": False}
    mock_step.return_value = {"id": "step_1"}

    session = WorkflowStateService.mark_step_complete("sess_1")

    assert session.current_state_id == "state_1"
    assert mock_apply.call_args.kwargs["step_id"] == "step_1"
    assert mock_apply.call_args.kwargs["next_state_id"] is None
    assert isinstance(mock_apply.call_args.kwargs["expected_updated_at"], datetime)


@patch("app.services.workflow_state.OWDRepository.record_analytics_event")
@patch("app.services.workflow_state.WorkflowSessionRepository.apply_progress")
@patch("app.services.workflow_state.OWDRepository.get_steps_for_state")
@patch("app.services.workflow_state.OWDRepository.get_next_state_transition")
@patch("app.services.workflow_state.OWDRepository.count_pending_steps", return_value=1)
@patch("app.services.workflow_state.OWDRepository.get_next_pending_step")
@patch("app.services.workflow_state.OWDRepository.get_state_by_id")
@patch("app.services.workflow_state.WorkflowSessionRepository.get_by_id")
def test_terminal_target_with_steps_remains_active_until_its_steps_run(
    mock_get,
    mock_state,
    mock_step,
    _mock_count,
    mock_transition,
    mock_target_steps,
    mock_apply,
    _mock_event,
):
    mock_get.side_effect = [session_row(), session_row(current_state_id="state_end")]
    mock_state.return_value = {"id": "state_1", "is_terminal": False}
    mock_step.return_value = {"id": "step_1"}
    mock_transition.return_value = {"to_state_id": "state_end", "is_terminal": True}
    mock_target_steps.return_value = [{"id": "final_step"}]

    session = WorkflowStateService.mark_step_complete("sess_1")

    assert session.current_state_id == "state_end"
    assert mock_apply.call_args.kwargs["new_status"] == "active"


@patch("app.services.workflow_state.OWDRepository.record_analytics_event")
@patch("app.services.workflow_state.WorkflowSessionRepository.apply_progress")
@patch("app.services.workflow_state.OWDRepository.get_steps_for_state", return_value=[])
@patch("app.services.workflow_state.OWDRepository.get_next_state_transition")
@patch("app.services.workflow_state.OWDRepository.count_pending_steps", return_value=1)
@patch("app.services.workflow_state.OWDRepository.get_next_pending_step")
@patch("app.services.workflow_state.OWDRepository.get_state_by_id")
@patch("app.services.workflow_state.WorkflowSessionRepository.get_by_id")
def test_empty_terminal_target_completes_on_entry(
    mock_get,
    mock_state,
    mock_step,
    _mock_count,
    mock_transition,
    _mock_target_steps,
    mock_apply,
    _mock_event,
):
    mock_get.side_effect = [session_row(), session_row(current_state_id="state_end", status="completed")]
    mock_state.return_value = {"id": "state_1", "is_terminal": False}
    mock_step.return_value = {"id": "step_1"}
    mock_transition.return_value = {"to_state_id": "state_end", "is_terminal": True}

    session = WorkflowStateService.mark_step_complete("sess_1")

    assert session.status == "completed"
    assert mock_apply.call_args.kwargs["new_status"] == "completed"


def test_transition_conditions_are_deterministic_and_do_not_eval_code():
    transitions = [
        {
            "id": "t1",
            "condition_type": "DECISION_OPTION",
            "condition_expression": "OPT_DAMAGED",
            "option_code": "OPT_DAMAGED",
            "option_label": "Damaged",
        },
        {"id": "fallback", "condition_type": "FALLBACK", "condition_expression": ""},
    ]
    selected = OWDRepository._select_transition(transitions, {"decision_option": "Damaged"})
    assert selected["id"] == "t1"
    assert OWDRepository._select_transition(transitions, {}) is None
    assert OWDRepository._select_transition(transitions, {"use_fallback": True})["id"] == "fallback"
    assert OWDRepository._expression_matches("approved == true", {"approved": "true"})
    assert not OWDRepository._expression_matches("__import__('os').system('id')", {})


app = FastAPI()
app.include_router(router, prefix="/api/v1")
client = TestClient(app)
OWNER_TOKEN = create_access_token("usr_owner", "employee", "dept_ops")
OTHER_TOKEN = create_access_token("usr_other", "employee", "dept_ops")


@patch("app.api.v1.copilot_session.WorkflowSessionRepository.get_by_id")
def test_employee_cannot_read_another_users_session(mock_get):
    mock_get.return_value = session_row()
    response = client.get(
        "/api/v1/copilot/session/sess_1",
        headers={"Authorization": f"Bearer {OTHER_TOKEN}"},
    )
    assert response.status_code == 403


@patch("app.api.v1.copilot_session.WorkflowStateService.pause_session")
@patch("app.api.v1.copilot_session.WorkflowSessionRepository.get_by_id")
def test_owner_can_pause_session(mock_get, mock_pause):
    mock_get.return_value = session_row()
    mock_pause.return_value = WorkflowSession(**session_row(status="paused"))
    response = client.post(
        "/api/v1/copilot/session/sess_1/pause",
        headers={"Authorization": f"Bearer {OWNER_TOKEN}"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "paused"


@patch("app.api.v1.copilot_session.WorkflowStateService.mark_step_complete")
@patch("app.api.v1.copilot_session.WorkflowSessionRepository.get_by_id")
def test_owner_advance_completes_real_step_explicitly(mock_get, mock_advance):
    mock_get.return_value = session_row()
    mock_advance.return_value = WorkflowSession(**session_row())
    with patch(
        "app.api.v1.copilot_session.WorkflowStateService.get_position",
        return_value=WorkflowPosition(
            state_id="state_2",
            state_title="Next state",
            state_type="ATOMIC_STEP",
            step_id="step_2",
            step_number=2,
            step_title="Record temperature",
        ),
    ):
        response = client.post(
            "/api/v1/copilot/session/sess_1/advance",
            headers={"Authorization": f"Bearer {OWNER_TOKEN}"},
            json={"decision_option": "Damaged", "use_fallback": False},
        )
    assert response.status_code == 200
    assert response.json()["active_step_number"] == 2
    mock_advance.assert_called_once_with(
        "sess_1",
        {
            "values": {},
            "rule_results": {},
            "use_fallback": False,
            "decision_option": "Damaged",
        },
    )
