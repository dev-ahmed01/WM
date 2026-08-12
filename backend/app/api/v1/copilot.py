"""FastAPI Router for WorkMate Copilot Message Endpoint."""

import logging
import re
from typing import Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query

from app.core.config import settings
from app.core.text_matching import fuzzy_relevance_score
from app.middleware.auth_middleware import get_current_user
from app.middleware.rbac_middleware import require_role
from app.models.copilot import (
    CopilotMessageRequest,
    CopilotResponse,
    CopilotSessionSummary,
    CopilotHistoryResponse,
    CopilotConversationDetail,
    CopilotHistoryMessage,
)
from app.repositories.conversation_repository import ConversationRepository
from app.repositories.knowledge_repository import KnowledgeRepository
from app.repositories.owd_repository import OWDRepository
from app.services.retrieval import RetrievalService
from app.services.validation import ResponseValidationService
from app.services.workflow_state import WorkflowCompletionResult, WorkflowStateService
from app.services.escalation import EscalationService
from app.services.analytics_service import AnalyticsService
from app.services.copilot_reasoning import CopilotReasoningService
from app.services.workflow_intent import WorkflowIntentService
from app.integrations.ai_gateway import AIGateway
from app.integrations.ai_provider import GeneratedAnswer

copilot_logger = logging.getLogger("copilot_services")

router = APIRouter(prefix="/copilot", tags=["WorkMate Copilot"])

_STEP_COMPLETION_COMMANDS = {
    "complete",
    "completed",
    "done",
    "finished",
    "next",
    "step complete",
    "step completed",
}


def _is_step_completion_message(message: str) -> bool:
    normalized = " ".join(re.findall(r"[a-z0-9]+", message.casefold()))
    return normalized in _STEP_COMPLETION_COMMANDS


def _completion_through_target(message: str) -> int | None:
    """Recognize an explicit attestation, never a question or a bare skip request."""
    normalized = " ".join(re.findall(r"[a-z0-9]+", message.casefold()))
    if "?" in message or not re.search(r"\b(?:complete|completed|finished|done)\b", normalized):
        return None
    match = re.search(
        r"\b(?:through|thru|up to|until)\s+(?:step\s*)?(\d+)\b", normalized
    )
    return int(match.group(1)) if match else None


def _claims_previous_steps_without_target(message: str) -> bool:
    normalized = " ".join(re.findall(r"[a-z0-9]+", message.casefold()))
    return bool(
        re.search(r"\b(?:complete|completed|finished|done)\b", normalized)
        and re.search(r"\b(?:previous|prior|earlier)\s+steps?\b", normalized)
        and _completion_through_target(message) is None
    )


def _requested_step_jump(message: str) -> int | None:
    normalized = " ".join(re.findall(r"[a-z0-9]+", message.casefold()))
    if not re.search(r"\b(?:skip|jump|go|move|advance)\b", normalized):
        return None
    match = re.search(r"\b(?:to\s+)?step\s*(\d+)\b", normalized)
    return int(match.group(1)) if match else None


def _claimed_current_step(message: str) -> int | None:
    """Recognize an employee's reported position, not a request to skip checks."""
    normalized = " ".join(re.findall(r"[a-z0-9]+", message.casefold()))
    match = re.search(
        r"\b(?:(?:i am|i m|im)\s+(?:currently\s+)?(?:working\s+|stuck\s+)?|"
        r"(?:currently|working|stuck)\s+)(?:at|on)\s+step\s*(\d+)\b",
        normalized,
    )
    return int(match.group(1)) if match else None


def _requested_sop_index(message: str) -> int | None:
    normalized = " ".join(re.findall(r"[a-z0-9]+", message.casefold()))
    match = re.search(r"\bsop\s*(?:number\s*)?(\d+)\b", normalized)
    return int(match.group(1)) if match else None


def _step_guidance(position: Any, *, advanced: bool = False) -> str:
    if position is None:
        return "Workflow completed." if advanced else "The workflow is ready."
    if position.step_id:
        prefix = "Step completed. Next step:" if advanced else "Current step:"
        return (
            f"{prefix} {position.step_title} "
            'When finished, type "done" or select Complete step to continue.'
        )
    if position.decision_options:
        choices = ", ".join(option.option_label for option in position.decision_options)
        return f"Step completed. Choose the next workflow outcome: {choices}."
    return "Workflow completed." if advanced else "The workflow has no pending step."


def _match_decision_option(message: str, options: list[Any]) -> str | None:
    """Map natural wording only when it uniquely matches a persisted graph option."""
    normalized = " ".join(re.findall(r"[a-z0-9]+", message.casefold()))
    for option in options:
        for exact_value in (option.option_code, option.option_label):
            if normalized == " ".join(re.findall(r"[a-z0-9]+", exact_value.casefold())):
                return option.option_code
    ranked = sorted(
        (
            (
                fuzzy_relevance_score(
                    message, f"{option.option_code} {option.option_label}"
                ),
                option.option_code,
            )
            for option in options
        ),
        reverse=True,
    )
    if not ranked or ranked[0][0] < 0.70:
        return None
    runner_up = ranked[1][0] if len(ranked) > 1 else 0.0
    return ranked[0][1] if ranked[0][0] - runner_up >= 0.20 else None


def _future_workflow_guidance(query: str, future_source: Dict[str, Any]) -> str:
    """Return only the verified instruction that is useful to the employee."""
    future_title = str(future_source.get("step_title") or "Workflow guidance")
    guidance = CopilotReasoningService.concise_extract(query, future_source)
    if not guidance:
        guidance = future_title
    return guidance


def _terminal_workflow_guidance(terminal_source: Dict[str, Any]) -> str:
    """Turn a persisted terminal state into a short, speakable completion reply."""
    title = str(terminal_source.get("step_title") or "").strip()
    if not title:
        title = CopilotReasoningService.concise_extract("", terminal_source)
    title = re.sub(r"\s*\([A-Z0-9_-]+\)\s*$", "", title).strip()
    subject = re.sub(r"\b(?:complete|completed|finished)\b.*$", "", title, flags=re.I).strip()
    return f"{subject or 'This workflow'} is now completed."


def _persist_control_reply(
    *,
    conversation_id: str,
    user_message_id: str,
    intent: str,
    answer: str,
    spoken_answer: Optional[str] = None,
    sop_details: Optional[str] = None,
    active_session: Any = None,
    position: Any = None,
) -> CopilotResponse:
    """Persist a deterministic reply backed by catalog or workflow state."""
    ConversationRepository.update_message_intent(user_message_id, intent)
    message_id = ConversationRepository.persist_message(
        conversation_id=conversation_id,
        sender="ai",
        content=answer,
        confidence_score=1.0,
    )
    return CopilotResponse(
        conversation_id=conversation_id,
        message_id=message_id,
        answer=answer,
        spoken_answer=spoken_answer,
        sop_details=sop_details,
        citations=[],
        confidence_score=1.0,
        is_grounded=True,
        requires_escalation=False,
        active_session_id=active_session.id if active_session else None,
        active_session_status=active_session.status if active_session else None,
        active_sop_id=active_session.workflow_version_id if active_session else None,
        active_step_number=position.step_number if position else None,
        active_step_title=position.step_title if position else None,
        active_decision_options=position.decision_options if position else [],
    )


async def _verified_followup_reply(
    *,
    message: str,
    prior_state_id: str,
    conversation_id: str,
    user_message_id: str,
    department_id: str,
    role: str,
    active_session: Any,
    position: Any,
    advance: bool = True,
) -> Optional[CopilotResponse]:
    """Follow a cited workflow node without trusting the model with graph authority."""
    transition = (
        OWDRepository.get_next_state_transition(prior_state_id, {}) if advance else None
    )
    source_state_id = (
        str(transition["to_state_id"])
        if transition and transition.get("to_state_id")
        else prior_state_id
    )
    if advance and not transition:
        return None
    next_source = await AIGateway.get_workflow_state_source(
        department_id, active_session.workflow_version_id, source_state_id
    )
    if not next_source:
        return None
    if not advance:
        instruction = CopilotReasoningService.concise_extract(message, next_source)
        answer = f"Before moving on, complete this verified instruction: {instruction}"
    else:
        answer = (
            _terminal_workflow_guidance(next_source)
            if bool(transition and transition.get("is_terminal"))
            else _future_workflow_guidance(message, next_source)
        )
    validated, requires_escalation = ResponseValidationService.validate_response(
        raw_response=GeneratedAnswer(
            answer=answer,
            source_ids=[str(next_source["chunk_id"])],
            provider="verified_conversation_followup",
        ),
        retrieved_chunks=[next_source],
        user_role=role,
        user_department_id=department_id,
    )
    if requires_escalation or not validated.is_grounded:
        return None
    ConversationRepository.update_message_intent(
        user_message_id, "WORKFLOW_VERIFIED_FOLLOWUP"
    )
    message_id = ConversationRepository.persist_message(
        conversation_id=conversation_id,
        sender="ai",
        content=validated.answer,
        confidence_score=validated.confidence_score,
        retrieved_state_ids=[str(next_source["state_id"])],
        citations=[citation.model_dump() for citation in validated.citations],
        escalated=False,
    )
    return CopilotResponse(
        conversation_id=conversation_id,
        message_id=message_id,
        answer=validated.answer,
        citations=validated.citations,
        confidence_score=validated.confidence_score,
        is_grounded=True,
        requires_escalation=False,
        active_session_id=active_session.id,
        active_session_status=active_session.status,
        active_sop_id=active_session.workflow_version_id,
        active_step_number=position.step_number,
        active_step_title=position.step_title,
        active_decision_options=position.decision_options,
    )


def _completion_reply(
    completion: Any, position: Any, target: int, *, mention_target: bool = True
) -> str:
    recorded = _recorded_completion_text(completion.completed_step_numbers)
    if completion.stopped_at_decision:
        continuation = (
            f"continue toward step {target}." if mention_target else "continue."
        )
        return (
            f"{recorded} A verified outcome is required before I can {continuation} "
            f"{_step_guidance(position, advanced=True)}"
        )
    return f"{recorded} {_step_guidance(position, advanced=True)}"


def _recorded_completion_text(completed: list[int]) -> str:
    if not completed:
        return "No additional steps were recorded."
    if len(completed) == 1:
        return f"Recorded your completion attestation for step {completed[0]}."
    return (
        f"Recorded your completion attestation for steps {completed[0]} "
        f"through {completed[-1]}."
    )


@router.get(
    "/history",
    response_model=CopilotHistoryResponse,
    summary="Get user's past Copilot conversation sessions",
    dependencies=[Depends(require_role("employee", "admin", "manager"))],
)
async def get_copilot_history(
    current_user: Dict[str, Any] = Depends(get_current_user),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> CopilotHistoryResponse:
    """Retrieves paginated list of past conversation sessions for the authenticated user."""
    user_id = current_user.get("sub", "")
    sessions_raw = ConversationRepository.list_user_conversations(user_id, limit=limit, offset=offset)
    total = ConversationRepository.count_user_conversations(user_id)

    sessions = [CopilotSessionSummary(**s) for s in sessions_raw]
    return CopilotHistoryResponse(sessions=sessions, total=total)


@router.get(
    "/history/{conversation_id}",
    response_model=CopilotConversationDetail,
    dependencies=[Depends(require_role("employee", "admin", "manager"))],
)
async def get_copilot_conversation(
    conversation_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> CopilotConversationDetail:
    if not ConversationRepository.belongs_to_user(conversation_id, current_user.get("sub", "")):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error_code": "NOT_FOUND",
                "message": f"Conversation '{conversation_id}' was not found.",
                "details": None,
            },
        )
    messages = [
        CopilotHistoryMessage(**message)
        for message in ConversationRepository.load_history(conversation_id, limit=200)
    ]
    active_session = WorkflowStateService.get_current_session(conversation_id)
    position = WorkflowStateService.get_position(active_session) if active_session else None
    return CopilotConversationDetail(
        conversation_id=conversation_id,
        messages=messages,
        active_session_id=active_session.id if active_session else None,
        active_session_status=active_session.status if active_session else None,
        active_sop_id=active_session.workflow_version_id if active_session else None,
        active_step_number=position.step_number if position else None,
        active_step_title=position.step_title if position else None,
        active_decision_options=position.decision_options if position else [],
    )


@router.post(
    "/message",
    response_model=CopilotResponse,
    summary="Send message to WorkMate Copilot",
    dependencies=[Depends(require_role("employee", "admin", "manager"))],
)
async def copilot_message(
    payload: CopilotMessageRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> CopilotResponse:
    """Core Copilot Orchestration Pipeline:
    1. Session & History Persistence
    2. Intent Detection & Ambiguity Check (short-circuit clarifying question if needed)
    3. Active Workflow Session Resolution & Step Progression Check
    4. Scoped Retrieval (Chunks & Active SOP Step Context)
    5. Local grounded response generation
    6. Response Validation Layer Gate (Grounding, Permissions, Citations, Confidence)
    7. Real Escalation Triggering (n8n Webhook) on Validation Failure
    8. Telemetry Recording (analytics_events)
    9. Return CopilotResponse matching exact frontend contract.
    """
    user_id = current_user.get("sub", "")
    role = current_user.get("role", "employee")
    department_id = current_user["department_id"]

    copilot_logger.info(f"Processing Copilot message for user '{user_id}' in department '{department_id}'")

    # 1. Session Resolution & Persist User Message
    conversation_id = ConversationRepository.get_or_create_session(
        user_id=user_id,
        department_id=department_id,
        session_id=payload.conversation_id,
    )
    user_message_id = ConversationRepository.persist_message(
        conversation_id=conversation_id,
        sender="employee",
        content=payload.message,
        confidence_score=0.0,
    )
    history: list[Dict[str, Any]] = []
    started_workflow_this_turn = False
    active_session = WorkflowStateService.get_current_session(conversation_id)
    resolved_position: Any = None
    prechecked_position: Any = None

    # Catalog selection is deterministic and remains available when embeddings
    # or the local model are slow. Only one unambiguous published match can run.
    requested_sop_index = _requested_sop_index(payload.message)
    catalog: list[Dict[str, Any]] = []
    should_check_catalog = bool(
        requested_sop_index is not None
        or WorkflowIntentService.is_workflow_request(payload.message)
        or (
            active_session is None
            and WorkflowIntentService.is_catalog_candidate(payload.message)
        )
    )
    if should_check_catalog:
        try:
            catalog = KnowledgeRepository.list_published_catalog(department_id)
        except Exception:
            copilot_logger.exception(
                "Published workflow catalog lookup failed; continuing with grounded retrieval"
            )

    if requested_sop_index is not None:
        sop_details = None
        catalog_position = requested_sop_index - 1
        if 0 <= catalog_position < len(catalog):
            item = catalog[catalog_position]
            description = str(item.get("description") or "").strip()
            answer = description or "This published SOP is available for guided execution."
            if description:
                answer = description
            answer += f' To begin guided execution, say "start {item["title"]}".'
            sop_details = (
                f"SOP {requested_sop_index}: {item['title']} | "
                f"{item['workflow_code']}"
            )
        elif catalog:
            available = ", ".join(
                f"{index + 1}. {item['title']}"
                for index, item in enumerate(catalog[:5])
            )
            answer = (
                f"SOP {requested_sop_index} is not available for your department. "
                f"Published SOPs: {available}."
            )
        else:
            answer = "No published SOPs are available for your department."
        position = WorkflowStateService.get_position(active_session) if active_session else None
        return _persist_control_reply(
            conversation_id=conversation_id,
            user_message_id=user_message_id,
            intent="SOP_CATALOG_LOOKUP",
            answer=answer,
            sop_details=sop_details,
            active_session=active_session,
            position=position,
        )

    workflow_match = WorkflowIntentService.match_published_workflow(
        payload.message, catalog
    )
    if workflow_match:
        sop_details = (
            f"SOP: {workflow_match['title']} | {workflow_match['workflow_code']}"
        )
        matched_version_id = str(workflow_match["workflow_version_id"])
        if active_session and active_session.workflow_version_id != matched_version_id:
            position = WorkflowStateService.get_position(active_session)
            answer = (
                "Another workflow is currently active. Pause or abandon it before "
                f"starting this SOP. {_step_guidance(position)}"
            )
            intent = "WORKFLOW_SELECTION_CONFLICT"
        else:
            if not active_session:
                active_session = WorkflowStateService.start_session(
                    conversation_id=conversation_id,
                    workflow_version_id=matched_version_id,
                    user_id=user_id,
                )
                started_workflow_this_turn = True
                intent = "WORKFLOW_START"
            else:
                intent = "WORKFLOW_RESUME"
            position = WorkflowStateService.get_position(active_session)
            answer = _step_guidance(position)
            if intent == "WORKFLOW_START":
                answer += (
                    " If you are already partway through, tell me your current step "
                    "or describe what you are stuck on and I will use that verified "
                    "guidance directly."
                )
        copilot_logger.info(
            "Resolved workflow catalog intent '%s' with score %.3f",
            intent,
            float(workflow_match.get("match_score") or 0.0),
        )
        return _persist_control_reply(
            conversation_id=conversation_id,
            user_message_id=user_message_id,
            intent=intent,
            answer=answer,
            spoken_answer=answer,
            sop_details=sop_details,
            active_session=active_session,
            position=position,
        )

    if active_session and active_session.status == "active":
        current_position = WorkflowStateService.get_position(active_session)
        prechecked_position = current_position
        if WorkflowIntentService.is_all_steps_completion(payload.message):
            final_step = OWDRepository.get_last_step_ordinal(
                active_session.workflow_version_id
            )
            if final_step is None:
                answer = f"This workflow has no executable steps. {_step_guidance(current_position)}"
                return _persist_control_reply(
                    conversation_id=conversation_id,
                    user_message_id=user_message_id,
                    intent="WORKFLOW_ALL_STEPS_COMPLETE",
                    answer=answer,
                    active_session=active_session,
                    position=current_position,
                )
            completion = WorkflowStateService.complete_through_step(
                active_session.id, final_step
            )
            active_session = completion.session
            next_position = WorkflowStateService.get_position(active_session)
            answer = _completion_reply(
                completion, next_position, final_step, mention_target=False
            )
            return _persist_control_reply(
                conversation_id=conversation_id,
                user_message_id=user_message_id,
                intent="WORKFLOW_ALL_STEPS_COMPLETE",
                answer=answer,
                active_session=active_session,
                position=next_position,
            )

        completion_target = _completion_through_target(payload.message)
        if completion_target is not None:
            completion = WorkflowStateService.complete_through_step(
                active_session.id, completion_target
            )
            active_session = completion.session
            next_position = WorkflowStateService.get_position(active_session)
            answer = _completion_reply(completion, next_position, completion_target)
            return _persist_control_reply(
                conversation_id=conversation_id,
                user_message_id=user_message_id,
                intent="WORKFLOW_MULTI_STEP_COMPLETE",
                answer=answer,
                active_session=active_session,
                position=next_position,
            )

        claimed_step = _claimed_current_step(payload.message)
        if claimed_step is not None:
            persisted_step = OWDRepository.get_step_by_ordinal(
                active_session.workflow_version_id, claimed_step
            )
            if persisted_step is None:
                answer = (
                    f"Step {claimed_step} is not present in this published SOP. "
                    f"{_step_guidance(current_position)}"
                )
                return _persist_control_reply(
                    conversation_id=conversation_id,
                    user_message_id=user_message_id,
                    intent="WORKFLOW_POSITION_INVALID",
                    answer=answer,
                    active_session=active_session,
                    position=current_position,
                )
            current_step_number = int(current_position.step_number or 0)
            if claimed_step <= current_step_number:
                answer = (
                    f"Using your reported position at step {claimed_step}. "
                    f"{_step_guidance(current_position)}"
                )
                return _persist_control_reply(
                    conversation_id=conversation_id,
                    user_message_id=user_message_id,
                    intent="WORKFLOW_POSITION_CONFIRMED",
                    answer=answer,
                    active_session=active_session,
                    position=current_position,
                )
            completion = WorkflowStateService.complete_through_step(
                active_session.id, claimed_step - 1
            )
            active_session = completion.session
            reported_position = WorkflowStateService.get_position(active_session)
            if reported_position.step_number == claimed_step:
                answer = (
                    f"{_recorded_completion_text(completion.completed_step_numbers)} "
                    f"Resuming at your reported position. {_step_guidance(reported_position)}"
                )
            else:
                answer = _completion_reply(
                    completion, reported_position, claimed_step, mention_target=True
                )
            return _persist_control_reply(
                conversation_id=conversation_id,
                user_message_id=user_message_id,
                intent="WORKFLOW_POSITION_RESUME",
                answer=answer,
                active_session=active_session,
                position=reported_position,
            )

        requested_step = _requested_step_jump(payload.message)
        if requested_step is not None:
            last_required_step = max(0, requested_step - 1)
            answer = (
                f"I will not silently skip operational checks to step {requested_step}. "
                f"If you already completed the preceding work, say \"complete through "
                f"step {last_required_step}\". I will record that attestation and stop "
                f"at any required decision. {_step_guidance(current_position)}"
            )
            return _persist_control_reply(
                conversation_id=conversation_id,
                user_message_id=user_message_id,
                intent="WORKFLOW_STEP_NAVIGATION",
                answer=answer,
                active_session=active_session,
                position=current_position,
            )

    # A short, explicit completion command belongs to the active state machine,
    # not to general intent detection or semantic retrieval.
    if active_session and active_session.status == "active":
        current_position = prechecked_position or WorkflowStateService.get_position(active_session)
        if current_position.step_id and _is_step_completion_message(payload.message):
            ConversationRepository.update_message_intent(
                user_message_id, "WORKFLOW_STEP_COMPLETE"
            )
            active_session = WorkflowStateService.mark_step_complete(active_session.id)
            next_position = WorkflowStateService.get_position(active_session)
            answer = _step_guidance(next_position, advanced=True)
            msg_id = ConversationRepository.persist_message(
                conversation_id=conversation_id,
                sender="ai",
                content=answer,
                confidence_score=1.0,
            )
            try:
                AnalyticsService.record_event(
                    event_type="copilot.workflow_step_completed",
                    conversation_message_id=msg_id,
                    payload={
                        "user_id": user_id,
                        "department_id": department_id,
                        "workflow_session_id": active_session.id,
                        "completed_step_id": current_position.step_id,
                    },
                )
            except Exception:
                copilot_logger.exception("Workflow completion telemetry write failed")
            return CopilotResponse(
                conversation_id=conversation_id,
                message_id=msg_id,
                answer=answer,
                citations=[],
                confidence_score=1.0,
                is_grounded=True,
                requires_escalation=False,
                active_session_id=active_session.id,
                active_session_status=active_session.status,
                active_sop_id=active_session.workflow_version_id,
                active_step_number=next_position.step_number,
                active_step_title=next_position.step_title,
                active_decision_options=next_position.decision_options,
            )

    # Load only bounded prior context after the fast completion-command path.
    # The just-persisted user message is excluded, and history is never evidence.
    history = [
        item
        for item in ConversationRepository.get_history(
            conversation_id, limit=settings.COPILOT_HISTORY_LIMIT + 1
        )
        if str(item.get("id")) != user_message_id
    ][-settings.COPILOT_HISTORY_LIMIT :]

    # A follow-up to the last cited instruction should use that persisted
    # provenance, even if broad semantic retrieval is slow or unavailable.
    if active_session and active_session.status == "active":
        prior_guidance = CopilotReasoningService.last_verified_instruction(history)
        if prior_guidance and CopilotReasoningService.should_reason_about_verified_followup(
            payload.message, prior_guidance["instruction"]
        ):
            followup_plan = await AIGateway.classify_verified_instruction_followup(
                payload.message, prior_guidance["instruction"]
            )
            if float(followup_plan.get("confidence") or 0.0) == 0.0:
                followup_plan = CopilotReasoningService.fallback_verified_followup_plan(
                    payload.message, prior_guidance["instruction"]
                )
            copilot_logger.info(
                "Verified follow-up plan relation=%s next=%s confidence=%.3f",
                followup_plan.get("relation"),
                bool(followup_plan.get("asks_next")),
                float(followup_plan.get("confidence") or 0.0),
            )
            followup_advances = CopilotReasoningService.verified_followup_is_actionable(
                payload.message, prior_guidance["instruction"], followup_plan
            )
            followup_reminds = CopilotReasoningService.verified_followup_needs_reminder(
                payload.message, followup_plan
            )
            if followup_advances or followup_reminds:
                planner_position = prechecked_position or WorkflowStateService.get_position(
                    active_session
                )
                followup_reply = await _verified_followup_reply(
                    message=payload.message,
                    prior_state_id=prior_guidance["state_id"],
                    conversation_id=conversation_id,
                    user_message_id=user_message_id,
                    department_id=department_id,
                    role=role,
                    active_session=active_session,
                    position=planner_position,
                    advance=followup_advances,
                )
                if followup_reply:
                    copilot_logger.info(
                        "Answered from persisted verified conversational provenance"
                    )
                    return followup_reply

    # Natural, context-dependent completion claims are interpreted by the local
    # model as a structured proposal. The model never receives graph identifiers
    # and cannot mutate state; persisted steps and options are validated below.
    if active_session and active_session.status == "active":
        planner_position = prechecked_position or WorkflowStateService.get_position(
            active_session
        )
        if CopilotReasoningService.should_plan_workflow_action(
            payload.message,
            history,
            str(planner_position.step_title or ""),
        ):
            planner_history, planner_context = (
                CopilotReasoningService.workflow_planner_context(
                    planner_position, history, settings.COPILOT_HISTORY_LIMIT
                )
            )
            workflow_plan = await AIGateway.plan_workflow_action(
                payload.message, planner_history, planner_context
            )
            plan_confidence = float(workflow_plan.get("confidence") or 0.0)
            if plan_confidence == 0.0:
                workflow_plan = CopilotReasoningService.fallback_workflow_plan(
                    payload.message, history
                )
                plan_confidence = float(workflow_plan["confidence"])
            completion_scope = str(
                workflow_plan.get("completion_scope") or "none"
            )
            outcome_text = str(workflow_plan.get("outcome_text") or "").strip()
            copilot_logger.info(
                "Structured workflow plan intent=%s scope=%s confidence=%.3f outcome=%s",
                workflow_plan.get("intent"),
                completion_scope,
                plan_confidence,
                bool(outcome_text),
            )

            completion = None
            if plan_confidence >= 0.72 and completion_scope != "none":
                if completion_scope == "current" and planner_position.step_id:
                    completed_number = int(planner_position.step_number or 0)
                    active_session = WorkflowStateService.mark_step_complete(
                        active_session.id,
                        {
                            "completion_attestation": "ai_interpreted_current_step",
                            "original_message": payload.message[:500],
                            "planner_confidence": plan_confidence,
                        },
                    )
                    completion = WorkflowCompletionResult(
                        session=active_session,
                        completed_step_numbers=(
                            [completed_number] if completed_number else []
                        ),
                    )
                elif completion_scope == "all_available":
                    final_step = OWDRepository.get_last_step_ordinal(
                        active_session.workflow_version_id
                    )
                    if final_step is not None:
                        completion = WorkflowStateService.complete_through_step(
                            active_session.id, final_step
                        )
                        active_session = completion.session

                if completion is not None:
                    planner_position = WorkflowStateService.get_position(active_session)
                    matched_option = (
                        _match_decision_option(
                            outcome_text, planner_position.decision_options
                        )
                        if outcome_text and planner_position.decision_options
                        else None
                    )
                    if matched_option:
                        selected_label = next(
                            option.option_label
                            for option in planner_position.decision_options
                            if option.option_code == matched_option
                        )
                        previous_state_id = active_session.current_state_id
                        active_session = (
                            WorkflowStateService.advance_if_transition_matches(
                                active_session.id,
                                {
                                    "decision_option": matched_option,
                                    "values": {
                                        "message": payload.message.strip(),
                                        "ai_interpreted_outcome": outcome_text,
                                    },
                                },
                            )
                        )
                        if active_session.current_state_id != previous_state_id:
                            next_position = WorkflowStateService.get_position(
                                active_session
                            )
                            answer = (
                                f"{_recorded_completion_text(completion.completed_step_numbers)} "
                                f"Outcome recorded: {selected_label}. "
                                f"{_step_guidance(next_position, advanced=True)}"
                            )
                            return _persist_control_reply(
                                conversation_id=conversation_id,
                                user_message_id=user_message_id,
                                intent="WORKFLOW_CONTEXTUAL_CONTINUATION",
                                answer=answer,
                                active_session=active_session,
                                position=next_position,
                            )

                    answer = _completion_reply(
                        completion,
                        planner_position,
                        int(planner_position.step_number or 1),
                        mention_target=False,
                    )
                    return _persist_control_reply(
                        conversation_id=conversation_id,
                        user_message_id=user_message_id,
                        intent="WORKFLOW_AI_INTERPRETED_COMPLETION",
                        answer=answer,
                        active_session=active_session,
                        position=planner_position,
                    )

    reasoning_move = CopilotReasoningService.classify_move(payload.message)
    retrieval_query = CopilotReasoningService.resolve_query(payload.message, history)
    retrieval_query = CopilotReasoningService.focus_operational_query(retrieval_query)

    # 2. Intent Detection & Clarification Check
    intent_result = await AIGateway.detect_intent(message=payload.message, history=history)
    detected_intent = str(intent_result.get("intent") or "GENERAL_QUERY")
    ConversationRepository.update_message_intent(user_message_id, detected_intent)
    if intent_result.get("needs_clarification"):
        position = WorkflowStateService.get_position(active_session) if active_session else None
        clarification_text = "Could you please specify which SOP or equipment section you are referring to?"
        msg_id = ConversationRepository.persist_message(
            conversation_id=conversation_id,
            sender="ai",
            content=clarification_text,
            confidence_score=0.0,
        )
        try:
            AnalyticsService.record_event(
                event_type="copilot.clarification",
                conversation_message_id=msg_id,
                payload={"user_id": user_id, "query": payload.message},
            )
        except Exception:
            copilot_logger.exception("Clarification telemetry write failed")
        return CopilotResponse(
            conversation_id=conversation_id,
            message_id=msg_id,
            answer=clarification_text,
            citations=[],
            confidence_score=0.0,
            is_grounded=False,
            requires_escalation=False,
            active_session_id=active_session.id if active_session else None,
            active_session_status=active_session.status if active_session else None,
            active_sop_id=active_session.workflow_version_id if active_session else None,
            active_step_number=position.step_number if position else None,
            active_step_title=position.step_title if position else None,
            active_decision_options=position.decision_options if position else [],
        )

    # 3. Resolve the workflow state. Natural wording may select one uniquely
    # matched persisted option, but it never marks an operational step complete.
    if active_session and active_session.status == "active":
        decision_position = WorkflowStateService.get_position(active_session)
        if decision_position.step_id:
            # An operational step cannot advance from conversational wording.
            resolved_position = decision_position
        else:
            decision_option = _match_decision_option(
                payload.message, decision_position.decision_options
            )
            previous_state_id = active_session.current_state_id
            active_session = WorkflowStateService.advance_if_transition_matches(
                active_session.id,
                {
                    "decision_option": decision_option or payload.message.strip(),
                    "values": {"message": payload.message.strip()},
                },
            )
            if active_session.current_state_id == previous_state_id:
                resolved_position = decision_position

    # 4. Prefer the authoritative active-state source for explanations and
    # matching exceptions. This avoids broad semantic retrieval for questions
    # the current workflow state can answer directly.
    precomputed_reasoned_answer: str | None = None
    retrieved_chunks: list[Dict[str, Any]] = []
    if (
        active_session
        and active_session.status == "active"
        and resolved_position
        and resolved_position.step_id
        and reasoning_move in {"reason", "exception", "explain"}
    ):
        active_source = await AIGateway.get_workflow_state_source(
            department_id,
            active_session.workflow_version_id,
            resolved_position.state_id,
        )
        if active_source:
            precomputed_reasoned_answer = CopilotReasoningService.active_step_answer(
                retrieval_query,
                reasoning_move,
                resolved_position,
                active_source,
            )
            if precomputed_reasoned_answer:
                retrieved_chunks = [active_source]

    if not retrieved_chunks:
        retrieved_chunks = await RetrievalService.retrieve_chunks(
            query=retrieval_query,
            department_id=department_id,
        )

    if (
        not active_session
        and ResponseValidationService.has_relevant_evidence(retrieved_chunks, department_id)
    ):
        workflow_version_id = retrieved_chunks[0].get("workflow_version_id")
        if workflow_version_id:
            active_session = WorkflowStateService.start_session(
                conversation_id=conversation_id,
                workflow_version_id=str(workflow_version_id),
                user_id=user_id,
            )
            started_workflow_this_turn = True

    # 5. Use deterministic persisted workflow guidance when the retrieved
    # source identifies the active state. This avoids waiting for a model to
    # regenerate text that already exists in the compiled workflow graph.
    position = (
        resolved_position
        or (WorkflowStateService.get_position(active_session) if active_session else None)
    )
    evidence_is_relevant = ResponseValidationService.has_relevant_evidence(
        retrieved_chunks, department_id
    )
    current_query_score = 0.0
    if active_session and position and evidence_is_relevant:
        current_source_index = next(
            (
                index
                for index, chunk in enumerate(retrieved_chunks)
                if str(chunk.get("workflow_version_id"))
                == active_session.workflow_version_id
                and str(chunk.get("state_id")) == position.state_id
            ),
            None,
        )
        if current_source_index is not None:
            current_query_score = float(
                retrieved_chunks[current_source_index].get("score") or 0.0
            )
            # The persisted active state is authoritative for current-step
            # guidance even when the user's question primarily matches a later state.
            retrieved_chunks[current_source_index] = {
                **retrieved_chunks[current_source_index],
                "score": 1.0,
            }
        else:
            current_source = await AIGateway.get_workflow_state_source(
                department_id,
                active_session.workflow_version_id,
                position.state_id,
            )
            if current_source:
                retrieved_chunks.append(current_source)
    workflow_source = next(
        (
            chunk
            for chunk in retrieved_chunks
            if active_session
            and position
            and str(chunk.get("workflow_version_id")) == active_session.workflow_version_id
            and str(chunk.get("state_id")) == position.state_id
        ),
        None,
    )
    future_candidates = [
        chunk
        for chunk in retrieved_chunks
        if active_session
        and not started_workflow_this_turn
        and position
        and position.step_id
        and str(chunk.get("workflow_version_id")) == active_session.workflow_version_id
        and str(chunk.get("state_id")) != position.state_id
        and int(chunk.get("step_number") or 0) > int(position.step_number or 0)
        and float(chunk.get("score") or 0.0)
        >= settings.COPILOT_MIN_CONFIDENCE_THRESHOLD
        and float(chunk.get("score") or 0.0) - current_query_score >= 0.20
    ]
    future_workflow_source = max(
        future_candidates,
        key=lambda chunk: (
            bool(
                CopilotReasoningService.evidence_sections(
                    str(chunk.get("content") or "")
                ).get("instructions")
            ),
            float(chunk.get("score") or 0.0),
            -int(chunk.get("step_number") or 0),
        ),
        default=None,
    )
    future_guidance_answer: Optional[str] = None
    if (
        future_workflow_source
        and active_session
        and CopilotReasoningService.describes_completed_action(
            retrieval_query, future_workflow_source
        )
    ):
        completed_state_id = str(future_workflow_source.get("state_id") or "")
        transition = OWDRepository.get_next_state_transition(completed_state_id, {})
        if transition and transition.get("to_state_id"):
            next_source = await AIGateway.get_workflow_state_source(
                department_id,
                active_session.workflow_version_id,
                str(transition["to_state_id"]),
            )
            if next_source:
                if not any(
                    str(chunk.get("chunk_id")) == str(next_source.get("chunk_id"))
                    for chunk in retrieved_chunks
                ):
                    retrieved_chunks.append(next_source)
                future_workflow_source = next_source
                if bool(transition.get("is_terminal")):
                    future_guidance_answer = _terminal_workflow_guidance(next_source)
                copilot_logger.info(
                    "Answered from verified state after user-completed state '%s'",
                    completed_state_id,
                )
    if not evidence_is_relevant:
        raw_response = GeneratedAnswer(answer="", source_ids=[], provider="none")
    elif future_workflow_source and workflow_source and position:
        raw_response = GeneratedAnswer(
            answer=future_guidance_answer
            or _future_workflow_guidance(retrieval_query, future_workflow_source),
            source_ids=[str(future_workflow_source["chunk_id"])],
            provider="workflow_deferred",
        )
    elif workflow_source and position and position.step_id:
        reasoned_answer = precomputed_reasoned_answer or (
            CopilotReasoningService.active_step_answer(
                retrieval_query,
                reasoning_move,
                position,
                workflow_source,
            )
        )
        raw_response = GeneratedAnswer(
            answer=reasoned_answer or position.step_title or "",
            source_ids=[str(workflow_source["chunk_id"])],
            provider="workflow_reasoned" if reasoned_answer else "workflow",
        )
    else:
        agent_context = CopilotReasoningService.agent_context(
            move=reasoning_move,
            history=history,
            position=position,
            role=role,
            department_id=department_id,
            history_limit=settings.COPILOT_HISTORY_LIMIT,
        )
        raw_response = await AIGateway.generate_response(
            {
                "user": current_user,
                "query": retrieval_query,
                "history": history,
                "agent_context": agent_context,
                "workflow_state": active_session.model_dump() if active_session else None,
                "retrieved_chunks": retrieved_chunks,
            }
        )

    # 6. Response Validation Layer Gate (Mandatory Pre-Delivery Gate)
    validated, requires_escalation = ResponseValidationService.validate_response(
        raw_response=raw_response,
        retrieved_chunks=retrieved_chunks,
        user_role=role,
        user_department_id=department_id,
    )

    cited_chunk_ids = {citation.chunk_id for citation in validated.citations}
    if (
        active_session
        and active_session.status == "active"
        and position
        and position.step_id
        and raw_response.provider not in {"workflow_deferred", "workflow_reasoned"}
        and validated.is_grounded
        and any(
            str(chunk.get("workflow_version_id")) == active_session.workflow_version_id
            and str(chunk.get("chunk_id")) in cited_chunk_ids
            for chunk in retrieved_chunks
        )
    ):
        validated.answer = _step_guidance(position)

    # 7. Persist AI Message & Trigger Real Escalation if required
    msg_id = ConversationRepository.persist_message(
        conversation_id=conversation_id,
        sender="ai",
        content=validated.answer,
        confidence_score=validated.confidence_score,
        retrieved_state_ids=[
            str(chunk["state_id"])
            for chunk in retrieved_chunks
            if chunk.get("state_id") and str(chunk.get("chunk_id")) in cited_chunk_ids
        ],
        citations=[citation.model_dump() for citation in validated.citations],
        escalated=requires_escalation,
    )

    if requires_escalation:
        escalation_service = EscalationService()
        try:
            await escalation_service.escalate(
                conversation_message_id=msg_id,
                reason=f"Low confidence ({validated.confidence_score}) or ungrounded response",
            )
        except Exception:
            # Escalation is an auditable side effect, but failure must not suppress
            # the mandatory grounded fallback response.
            copilot_logger.exception("Escalation persistence or notification failed")

    # 8. Record Telemetry Event
    try:
        AnalyticsService.record_event(
            event_type="copilot.turn",
            conversation_message_id=msg_id,
            payload={
                "user_id": user_id,
                "department_id": department_id,
                "confidence_score": validated.confidence_score,
                "requires_escalation": requires_escalation,
                "workflow_session_id": active_session.id if active_session else None,
            },
        )
    except Exception:
        copilot_logger.exception("Copilot telemetry write failed")

    # 9. Return CopilotResponse matching frontend contract
    return CopilotResponse(
        conversation_id=conversation_id,
        message_id=msg_id,
        answer=validated.answer,
        citations=validated.citations,
        confidence_score=validated.confidence_score,
        is_grounded=validated.is_grounded,
        requires_escalation=requires_escalation,
        active_session_id=active_session.id if active_session else None,
        active_session_status=active_session.status if active_session else None,
        active_sop_id=active_session.workflow_version_id if active_session else None,
        active_step_number=position.step_number if position else None,
        active_step_title=position.step_title if position else None,
        active_decision_options=position.decision_options if position else [],
    )
