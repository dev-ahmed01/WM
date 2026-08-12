"""Regression tests for grounded conversational reasoning behavior."""

from app.models.workflow_session import WorkflowPosition
from app.services.copilot_reasoning import CopilotReasoningService


def position() -> WorkflowPosition:
    return WorkflowPosition(
        state_id="state_1",
        state_title="Dock Arrival and Seal Inspection",
        state_type="ATOMIC_STEP",
        step_id="step_1",
        step_number=1,
        step_title="Verify physical trailer door seal number against Bill of Lading manifest.",
    )


def source():
    return {
        "content": (
            "Title: Receiving | State: Dock Arrival and Seal Inspection | "
            "Instructions: STEP_CHECK_SEAL Verify physical trailer door seal number "
            "against Bill of Lading manifest. | Rules: RULE_SEAL_HARD_STOP Broken seal "
            "or tag mismatch requires immediate driver hold and QA escalation. | "
            "Keywords: SEAL, MISMATCH"
        )
    }


def test_follow_up_query_inherits_last_employee_topic_not_ai_answer():
    history = [
        {"sender": "employee", "content": "What if the seal number does not match?"},
        {"sender": "ai", "content": "Current step: verify the seal."},
    ]

    resolved = CopilotReasoningService.resolve_query("Why?", history)

    assert resolved == "What if the seal number does not match? Follow-up: Why?"


def test_active_step_reasoning_explains_verified_hard_stop_without_invention():
    answer = CopilotReasoningService.active_step_answer(
        "Why do I need to check the seal?", "reason", position(), source()
    )

    assert answer is not None
    assert answer.startswith(
        "Broken seal or tag mismatch requires immediate driver hold and QA escalation."
    )
    assert "Current step remains: Verify physical trailer door seal" in answer


def test_reasoning_does_not_apply_current_rule_to_an_unrelated_topic():
    answer = CopilotReasoningService.active_step_answer(
        "Why is the forklift battery empty?", "reason", position(), source()
    )

    assert answer is None


def test_exception_reasoning_uses_rule_only_when_query_matches_it():
    matching = CopilotReasoningService.active_step_answer(
        "What if the seal number is a mismatch?", "exception", position(), source()
    )
    unrelated = CopilotReasoningService.active_step_answer(
        "What if the forklift battery is empty?", "exception", position(), source()
    )

    assert matching is not None
    assert unrelated is None


def test_positive_match_wording_does_not_trigger_mismatch_rule():
    answer = CopilotReasoningService.active_step_answer(
        "What if the seal matches the manifest?", "exception", position(), source()
    )

    assert answer is None


def test_concise_extract_never_dumps_serialized_metadata():
    answer = CopilotReasoningService.concise_extract(
        "What if the seal is broken?", source()
    )

    assert answer == (
        "Broken seal or tag mismatch requires immediate driver hold and QA escalation."
    )
    assert "Title:" not in answer
    assert "Keywords:" not in answer


def test_completed_future_action_can_request_the_verified_following_step():
    future_source = {
        "content": (
            "State: Quality Quarantine Hold | Instructions: STEP_APPLY_TAPE "
            "Apply physical red quarantine tape to damaged pallet and transport to Bay Q-1."
        )
    }

    assert CopilotReasoningService.describes_completed_action(
        "I have transported the packages to bay q 1; what should I do next?",
        future_source,
    )
    assert not CopilotReasoningService.describes_completed_action(
        "Should I transport the packages to bay q 1 next?",
        future_source,
    )


def test_agent_context_marks_history_separately_from_workflow_authority():
    context = CopilotReasoningService.agent_context(
        move="reason",
        history=[{"sender": "employee", "content": "Why?"}],
        position=position(),
        role="employee",
        department_id="dept_inbound",
        history_limit=6,
    )

    assert context["conversation_move"] == "reason"
    assert context["conversation_history"] == [{"role": "user", "content": "Why?"}]
    assert context["workflow_context"]["current_step_number"] == 1
    assert context["caller_context"] == {
        "role": "employee",
        "department_id": "dept_inbound",
    }


def test_ambiguous_completion_attestation_is_routed_to_semantic_planner():
    history = [
        {"sender": "employee", "content": "Packages are damaged. What should I do?"},
        {"sender": "ai", "content": "That is handled after the current checks."},
    ]

    assert CopilotReasoningService.should_plan_workflow_action(
        "I have done all this tasks tell me what should I do about", history
    )
    assert CopilotReasoningService.should_plan_workflow_action(
        "I complted all these taks; what about it", history
    )
    assert CopilotReasoningService.should_plan_workflow_action(
        "turn on the previous steps tell me what's further", history
    )
    assert CopilotReasoningService.should_plan_workflow_action(
        "finished verifying physical trailer told seal number",
        history,
        "Verify physical trailer door seal number against Bill of Lading manifest.",
    )
    assert not CopilotReasoningService.should_plan_workflow_action(
        "Are all these tasks done?", history
    )


def test_discourse_fallback_preserves_prior_employee_issue_without_inventing_action():
    history = [
        {"sender": "employee", "content": "packages damaged what should I do"},
        {"sender": "ai", "content": "Damage is evaluated after the current checks."},
    ]

    plan = CopilotReasoningService.fallback_workflow_plan(
        "I have done all this tasks tell me what should I do about", history
    )

    assert plan["completion_scope"] == "all_available"
    assert plan["outcome_text"] == "packages damaged what should i do"
    assert plan["confidence"] == 0.74
    assert plan["authoritative"] is False


def test_discourse_fallback_skips_control_chatter_to_find_operational_issue():
    history = [
        {"sender": "employee", "content": "the packages damage what should I do"},
        {"sender": "ai", "content": "Verified damage guidance is available later."},
        {
            "sender": "employee",
            "content": "turn on the previous steps tell me what's further",
        },
        {"sender": "ai", "content": "Please clarify."},
    ]

    plan = CopilotReasoningService.fallback_workflow_plan(
        "I have done the previous steps", history
    )

    assert plan["completion_scope"] == "all_available"
    assert plan["outcome_text"] == "packages damage what should i do"
