"""FastAPI Router for WorkMate Copilot Message Endpoint."""

import logging
from typing import Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, Query

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

copilot_logger = logging.getLogger("copilot_services")

router = APIRouter(prefix="/copilot", tags=["WorkMate Copilot"])


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
    history = ConversationRepository.get_history(conversation_id)
    active_session = WorkflowStateService.get_current_session(conversation_id)

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

    # 3. Resolve the workflow state. A chat message may select an exact persisted
    # decision option, but it never marks an operational step complete implicitly.
    if active_session and active_session.status == "active":
        active_session = WorkflowStateService.advance_if_transition_matches(
            active_session.id,
            {
                "decision_option": payload.message.strip(),
                "values": {"message": payload.message.strip()},
            },
        )

    # 4. Scoped Retrieval (Published Chunks & Department Scoped)
    retrieved_chunks = await RetrievalService.retrieve_chunks(
        query=payload.message,
        department_id=department_id,
    )

    if (
        not active_session
        and detected_intent == "SOP_GUIDANCE"
        and ResponseValidationService.has_relevant_evidence(retrieved_chunks, department_id)
    ):
        workflow_version_id = retrieved_chunks[0].get("workflow_version_id")
        if workflow_version_id:
            active_session = WorkflowStateService.start_session(
                conversation_id=conversation_id,
                workflow_version_id=str(workflow_version_id),
                user_id=user_id,
            )

    # 5. Context assembly and local grounded generation
    prompt_context = {
        "user": current_user,
        "query": payload.message,
        "history": history,
        "workflow_state": active_session.model_dump() if active_session else None,
        "retrieved_chunks": retrieved_chunks,
    }
    raw_response = await AIGateway.generate_response(prompt_context)

    # 6. Response Validation Layer Gate (Mandatory Pre-Delivery Gate)
    validated, requires_escalation = ResponseValidationService.validate_response(
        raw_response=raw_response,
        retrieved_chunks=retrieved_chunks,
        user_role=role,
        user_department_id=department_id,
    )

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
    position = WorkflowStateService.get_position(active_session) if active_session else None
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
