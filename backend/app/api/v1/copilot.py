"""FastAPI Router for WorkMate Copilot Message Endpoint."""

import logging
import re
from typing import Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, Query

from app.core.config import settings
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
from app.services.retrieval import RetrievalService
from app.services.validation import ResponseValidationService
from app.services.workflow_state import WorkflowStateService
from app.services.escalation import EscalationService
from app.services.analytics_service import AnalyticsService
from app.integrations.ai_gateway import AIGateway
from app.integrations.ai_provider import GeneratedAnswer
from app.integrations.retrieval_providers import fuzzy_relevance_score

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


def _deferred_workflow_guidance(position: Any, future_source: Dict[str, Any]) -> str:
    future_title = str(future_source.get("step_title") or "Later workflow guidance")
    future_number = future_source.get("step_number")
    return (
        f"{future_title} is handled at workflow step {future_number}. "
        f"Do not skip ahead. {_step_guidance(position)}"
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
    # Current local intent/generation providers do not consume history. Avoid a
    # redundant Snowflake round-trip on every interactive turn.
    history: list[Dict[str, Any]] = []
    active_session = WorkflowStateService.get_current_session(conversation_id)
    resolved_position: Any = None

    # A short, explicit completion command belongs to the active state machine,
    # not to general intent detection or semantic retrieval.
    if active_session and active_session.status == "active":
        current_position = WorkflowStateService.get_position(active_session)
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

    # 4. Scoped Retrieval (Published Chunks & Department Scoped)
    retrieved_chunks = await RetrievalService.retrieve_chunks(
        query=payload.message,
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
    future_workflow_source = next(
        (
            chunk
            for chunk in retrieved_chunks
            if active_session
            and position
            and position.step_id
            and str(chunk.get("workflow_version_id")) == active_session.workflow_version_id
            and str(chunk.get("state_id")) != position.state_id
            and int(chunk.get("step_number") or 0) > int(position.step_number or 0)
            and float(chunk.get("score") or 0.0)
            >= settings.COPILOT_MIN_CONFIDENCE_THRESHOLD
            and float(chunk.get("score") or 0.0) - current_query_score >= 0.20
        ),
        None,
    )
    if not evidence_is_relevant:
        raw_response = GeneratedAnswer(answer="", source_ids=[], provider="none")
    elif future_workflow_source and workflow_source and position:
        raw_response = GeneratedAnswer(
            answer=_deferred_workflow_guidance(position, future_workflow_source),
            source_ids=[
                str(future_workflow_source["chunk_id"]),
                str(workflow_source["chunk_id"]),
            ],
            provider="workflow_deferred",
        )
    elif workflow_source and position and position.step_id:
        raw_response = GeneratedAnswer(
            answer=position.step_title or "",
            source_ids=[str(workflow_source["chunk_id"])],
            provider="workflow",
        )
    else:
        raw_response = await AIGateway.generate_response(
            {
                "user": current_user,
                "query": payload.message,
                "history": history,
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
        and raw_response.provider != "workflow_deferred"
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
            if chunk.get("state_id")
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
