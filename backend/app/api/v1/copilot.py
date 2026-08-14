"""FastAPI Router for WorkMate Copilot Message Endpoint."""

import logging
import re
import tempfile
import time
from pathlib import Path
from difflib import SequenceMatcher
from typing import Dict, Any, Optional
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status, Query
from fastapi.responses import FileResponse
from starlette.concurrency import run_in_threadpool

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
    SopSuggestion,
)
from app.models.voice import (
    VoiceCopilotResponse,
    VoiceSynthesisRequest,
    VoiceSynthesisResponse,
)
from app.repositories.conversation_repository import ConversationRepository
from app.repositories.knowledge_repository import KnowledgeRepository
from app.repositories.owd_repository import OWDRepository
from app.repositories.query_resolution_repository import QueryResolutionRepository
from app.repositories.voice_repository import VoiceRepository
from app.services.retrieval import RetrievalService
from app.services.validation import ResponseValidationService
from app.services.workflow_state import WorkflowCompletionResult, WorkflowStateService
from app.services.speech_recognition_service import (
    FasterWhisperSpeechRecognitionService,
    SpeechRecognitionError,
    get_speech_recognition_service,
)
from app.services.text_to_speech_service import (
    PiperTextToSpeechService,
    TextToSpeechError,
    get_text_to_speech_service,
)
from app.services.translation_service import (
    SUPPORTED_LANGUAGES,
    TranslationError,
    TranslationService,
    get_translation_service,
)
from app.services.escalation import EscalationService
from app.services.analytics_service import AnalyticsService
from app.services.copilot_reasoning import CopilotReasoningService
from app.services.workflow_intent import WorkflowIntentService
from app.services.query_resolution_memory import (
    QueryResolutionMemoryService,
    normalized_query_key,
)
from app.integrations.ai_gateway import AIGateway
from app.integrations.ai_provider import GeneratedAnswer

copilot_logger = logging.getLogger("copilot_services")

router = APIRouter(prefix="/copilot", tags=["WorkMate Copilot"])

_VOICE_CONTENT_TYPES = {
    "audio/flac", "audio/m4a", "audio/mp3", "audio/mp4", "audio/mpeg",
    "audio/ogg", "audio/wav", "audio/webm", "audio/x-m4a", "audio/x-wav",
    "video/mp4", "video/webm", "application/octet-stream",
}


async def _save_voice_upload(audio: UploadFile) -> Path:
    content_type = (
        (audio.content_type or "application/octet-stream")
        .split(";", 1)[0]
        .strip()
        .casefold()
    )
    if content_type not in _VOICE_CONTENT_TYPES:
        copilot_logger.warning(
            "Rejected voice upload content type raw=%r normalized=%r filename=%r",
            audio.content_type,
            content_type,
            audio.filename,
        )
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail={
                "error_code": "VOICE_AUDIO_TYPE_UNSUPPORTED",
                "message": "Upload a WAV, MP3, M4A, FLAC, OGG, MP4, or WebM audio file.",
            },
        )
    suffix = Path(audio.filename or "voice.webm").suffix.lower() or ".webm"
    temporary = tempfile.NamedTemporaryFile(
        prefix="workmate_voice_", suffix=suffix, delete=False
    )
    total = 0
    try:
        while chunk := await audio.read(1024 * 1024):
            total += len(chunk)
            if total > settings.VOICE_MAX_AUDIO_BYTES:
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail={
                        "error_code": "VOICE_AUDIO_TOO_LARGE",
                        "message": (
                            f"Audio exceeds the {settings.VOICE_MAX_AUDIO_BYTES // (1024 * 1024)} MB limit."
                        ),
                    },
                )
            temporary.write(chunk)
        if total == 0:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "error_code": "VOICE_AUDIO_EMPTY",
                    "message": "The uploaded audio file is empty.",
                },
            )
        return Path(temporary.name)
    except Exception:
        Path(temporary.name).unlink(missing_ok=True)
        raise
    finally:
        temporary.close()
        await audio.close()

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
    if normalized in _STEP_COMPLETION_COMMANDS:
        return True
    tokens = normalized.split()
    if (
        not tokens
        or len(tokens) > 4
        or "?" in message
        or set(tokens) & {"not", "never", "cannot", "cant", "havent"}
        or tokens[0] in {"are", "can", "could", "is", "should", "would"}
    ):
        return False
    completion_words = ("complete", "completed", "done", "finished")
    return any(
        len(token) >= 3
        and token[0] == candidate[0]
        and SequenceMatcher(None, token, candidate).ratio() >= 0.78
        for token in tokens
        for candidate in completion_words
    )


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


def _workflow_confirmation_explanation(
    message: str, workflow: Dict[str, Any]
) -> str:
    """Summarize verified scope without exposing the SOP title; stay under 15 words."""
    raw_context = next(
        (
            str(workflow.get(field) or "").strip()
            for field in ("description", "state_title", "step_title")
            if str(workflow.get(field) or "").strip()
        ),
        "Verified operational guidance",
    )
    context_words = re.findall(r"[A-Za-z0-9'-]+", raw_context)[:9]
    context = " ".join(context_words).rstrip(".,;:")
    return f"{context}. Start it? Yes or no."


async def _localized_text(text: str, language: str | None) -> str:
    """Preserve the language of a localized menu selection and its follow-ups."""
    if not language or language == "en":
        return text
    try:
        return await get_translation_service().translate_from_english(text, language)
    except TranslationError:
        copilot_logger.exception("Could not localize Copilot control response")
        return text


def _create_pending_resolution(
    *,
    payload: CopilotMessageRequest,
    workflow: Dict[str, Any],
    department_id: str,
    conversation_id: str,
    user_message_id: str,
    user_id: str,
) -> str | None:
    """Persist a candidate mapping; it is not reusable until the user confirms."""
    translated_query = payload.message.strip()
    original_query = (payload.original_query or translated_query).strip()
    try:
        return QueryResolutionRepository.create_pending(
            department_id=department_id,
            original_query=original_query,
            normalized_query=normalized_query_key(translated_query),
            original_language=payload.response_language or "en",
            translated_query=translated_query,
            workflow_version_id=str(workflow["workflow_version_id"]),
            workflow_code=str(workflow["workflow_code"]),
            conversation_id=conversation_id,
            source_message_id=user_message_id,
            resolved_by=user_id,
        )
    except Exception:
        # Guidance remains available if optional learning persistence is degraded.
        copilot_logger.exception("Could not persist pending query resolution")
        return None


def _naturalize_sop_coverage(coverage: str) -> str:
    """Make persisted SOP summary text conversational without adding facts."""
    normalized = " ".join(coverage.strip().split()).rstrip(".")
    if not normalized:
        return "the verified operational steps for this process"
    first_word = normalized.split(maxsplit=1)[0].casefold()
    if first_word in {
        "apply", "check", "create", "handle", "inspect", "log", "manage",
        "move", "pack", "pick", "receive", "record", "register", "replenish",
        "scrap", "ship", "transfer", "verify",
    }:
        return f"how to {normalized[0].lower()}{normalized[1:]}"
    return f"{normalized[0].lower()}{normalized[1:]}"


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
    message_intent: Optional[str] = None,
    sop_suggestions: Optional[list[SopSuggestion]] = None,
    confidence_score: float = 1.0,
) -> CopilotResponse:
    """Persist a deterministic reply backed by catalog or workflow state."""
    ConversationRepository.update_message_intent(user_message_id, intent)
    message_id = ConversationRepository.persist_message(
        conversation_id=conversation_id,
        sender="ai",
        content=answer,
        intent=message_intent,
        confidence_score=confidence_score,
    )
    return CopilotResponse(
        conversation_id=conversation_id,
        message_id=message_id,
        answer=answer,
        spoken_answer=spoken_answer,
        sop_details=sop_details,
        citations=[],
        confidence_score=confidence_score,
        is_grounded=True,
        requires_escalation=False,
        active_session_id=active_session.id if active_session else None,
        active_session_status=active_session.status if active_session else None,
        active_sop_id=active_session.workflow_version_id if active_session else None,
        active_step_number=position.step_number if position else None,
        active_step_title=position.step_title if position else None,
        active_decision_options=position.decision_options if position else [],
        sop_suggestions=sop_suggestions or [],
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


@router.post(
    "/voice",
    response_model=VoiceCopilotResponse,
    summary="Send multilingual speech to WorkMate Copilot",
    dependencies=[Depends(require_role("employee", "admin", "manager"))],
)
async def copilot_voice(
    audio: UploadFile = File(...),
    language: str = Form("auto"),
    conversation_id: Optional[str] = Form(None),
    synthesize: bool = Form(True),
    current_user: Dict[str, Any] = Depends(get_current_user),
    speech_service: FasterWhisperSpeechRecognitionService = Depends(
        get_speech_recognition_service
    ),
    translation_service: TranslationService = Depends(get_translation_service),
    speech_output: PiperTextToSpeechService = Depends(get_text_to_speech_service),
) -> VoiceCopilotResponse:
    """Transcribe, translate, reason with the grounded Copilot, and speak the reply."""
    if not settings.VOICE_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error_code": "VOICE_DISABLED",
                "message": "The multilingual voice service is disabled.",
            },
        )
    selected_language = language.strip().casefold()
    allowed = {item.strip() for item in settings.VOICE_SUPPORTED_LANGUAGES.split(",")}
    if selected_language != "auto" and selected_language not in allowed:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error_code": "VOICE_LANGUAGE_UNSUPPORTED",
                "message": f"Supported languages: auto, {', '.join(sorted(allowed))}.",
            },
        )

    user_id = str(current_user.get("sub") or "")
    department_id = str(current_user["department_id"])
    temporary_path = await _save_voice_upload(audio)
    try:
        resolved_conversation_id = await run_in_threadpool(
            ConversationRepository.get_or_create_session,
            user_id,
            department_id,
            conversation_id,
        )
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise
    transcript = ""
    translated_transcript = ""
    detected_language = selected_language if selected_language != "auto" else "und"
    transcription_confidence = 0.0
    transcription_ms = translation_ms = synthesis_ms = 0
    audio_id: str | None = None
    response_message_id: str | None = None
    response_text = ""

    async def persist_failed_interaction(error_code: str) -> None:
        try:
            await run_in_threadpool(
                VoiceRepository.persist_interaction,
                conversation_id=resolved_conversation_id,
                response_message_id=response_message_id,
                user_id=user_id,
                original_language=detected_language,
                translated_language="en",
                original_transcript=transcript,
                translated_transcript=translated_transcript,
                response_text=response_text,
                transcription_confidence=transcription_confidence,
                transcription_ms=transcription_ms,
                translation_ms=translation_ms,
                synthesis_ms=synthesis_ms,
                audio_id=None,
                success=False,
            )
            await run_in_threadpool(
                AnalyticsService.record_event,
                "copilot.voice.failed",
                response_message_id,
                None,
                {
                    "user_id": user_id,
                    "department_id": department_id,
                    "language": detected_language,
                    "transcription_success": bool(transcript),
                    "error_code": error_code,
                    "transcription_ms": transcription_ms,
                    "translation_ms": translation_ms,
                    "synthesis_ms": synthesis_ms,
                },
            )
        except Exception:
            copilot_logger.exception("Failed voice interaction telemetry write failed")

    try:
        started = time.perf_counter()
        transcription = await speech_service.transcribe(
            temporary_path,
            None if selected_language == "auto" else selected_language,
        )
        transcription_ms = round((time.perf_counter() - started) * 1000)
        transcript = transcription.transcript
        detected_language = transcription.language.casefold()
        transcription_confidence = transcription.confidence
        if detected_language not in SUPPORTED_LANGUAGES or detected_language not in allowed:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "error_code": "VOICE_LANGUAGE_UNSUPPORTED",
                    "message": (
                        f"Detected language '{detected_language}' is not enabled. "
                        f"Supported languages: {', '.join(sorted(allowed))}."
                    ),
                },
            )

        started = time.perf_counter()
        translated_transcript = await translation_service.translate_to_english(
            transcript, detected_language
        )
        translation_ms = round((time.perf_counter() - started) * 1000)

        copilot_response = await copilot_message(
            CopilotMessageRequest(
                conversation_id=resolved_conversation_id,
                message=translated_transcript,
            ),
            current_user,
        )
        response_message_id = copilot_response.message_id

        if detected_language == "en":
            response_text = copilot_response.answer
            translated_copilot = copilot_response
        else:
            started = time.perf_counter()
            suggestions = copilot_response.sop_suggestions
            translated_suggestions = []
            if suggestions:
                fields = [copilot_response.answer]
                for suggestion in suggestions:
                    fields.extend([suggestion.title, suggestion.description])
                translated_fields = await translation_service.translate_many_from_english(
                    fields, detected_language
                )
                response_text = translated_fields[0]
                for index, suggestion in enumerate(suggestions):
                    translated_suggestions.append(
                        suggestion.model_copy(
                            update={
                                "title": translated_fields[1 + index * 2],
                                "description": translated_fields[2 + index * 2],
                            }
                        )
                    )
            else:
                response_text = await translation_service.translate_from_english(
                    copilot_response.answer, detected_language
                )
            translation_ms += round((time.perf_counter() - started) * 1000)
            translated_copilot = copilot_response.model_copy(
                update={
                    "answer": response_text,
                    "spoken_answer": response_text,
                    "sop_suggestions": translated_suggestions,
                }
            )

        if synthesize and speech_output.supports(detected_language):
            started = time.perf_counter()
            audio_id = await speech_output.synthesize(response_text, detected_language)
            synthesis_ms = round((time.perf_counter() - started) * 1000)
        else:
            copilot_logger.warning(
                "No Piper voice configured for detected language '%s'; returning text only",
                detected_language,
            )

        await run_in_threadpool(
            VoiceRepository.persist_interaction,
            conversation_id=resolved_conversation_id,
            response_message_id=response_message_id,
            user_id=user_id,
            original_language=detected_language,
            translated_language="en",
            original_transcript=transcript,
            translated_transcript=translated_transcript,
            response_text=response_text,
            transcription_confidence=transcription_confidence,
            transcription_ms=transcription_ms,
            translation_ms=translation_ms,
            synthesis_ms=synthesis_ms,
            audio_id=audio_id,
            success=True,
        )
        try:
            await run_in_threadpool(
                AnalyticsService.record_event,
                "copilot.voice",
                response_message_id,
                None,
                {
                    "user_id": user_id,
                    "department_id": department_id,
                    "language": detected_language,
                    "transcription_success": True,
                    "transcription_confidence": transcription_confidence,
                    "transcription_ms": transcription_ms,
                    "translation_ms": translation_ms,
                    "synthesis_ms": synthesis_ms,
                    "audio_generated": bool(audio_id),
                },
            )
        except Exception:
            copilot_logger.exception("Voice telemetry write failed")

        return VoiceCopilotResponse(
            language=detected_language,
            transcript=transcript,
            translated_transcript=translated_transcript,
            response_text=response_text,
            audio_url=(f"/copilot/voice/audio/{audio_id}" if audio_id else None),
            confidence=transcription_confidence,
            transcription_ms=transcription_ms,
            translation_ms=translation_ms,
            synthesis_ms=synthesis_ms,
            copilot=translated_copilot,
        )
    except HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, dict) else {}
        error_code = str(detail.get("error_code") or "VOICE_REQUEST_FAILED")
        if transcript:
            await persist_failed_interaction(error_code)
        raise
    except SpeechRecognitionError as exc:
        copilot_logger.warning("Voice transcription failed: %s", exc)
        await persist_failed_interaction("VOICE_TRANSCRIPTION_FAILED")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error_code": "VOICE_TRANSCRIPTION_FAILED", "message": str(exc)},
        ) from exc
    except TranslationError as exc:
        copilot_logger.exception("Voice translation failed")
        await persist_failed_interaction("VOICE_TRANSLATION_FAILED")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"error_code": "VOICE_TRANSLATION_FAILED", "message": str(exc)},
        ) from exc
    except TextToSpeechError as exc:
        copilot_logger.exception("Voice synthesis failed")
        await persist_failed_interaction("VOICE_SYNTHESIS_FAILED")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"error_code": "VOICE_SYNTHESIS_FAILED", "message": str(exc)},
        ) from exc
    finally:
        temporary_path.unlink(missing_ok=True)


@router.post(
    "/voice/speech",
    response_model=VoiceSynthesisResponse,
    summary="Generate speech for a completed voice response",
    dependencies=[Depends(require_role("employee", "admin", "manager"))],
)
async def synthesize_voice_response(
    request: VoiceSynthesisRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
    speech_output: PiperTextToSpeechService = Depends(get_text_to_speech_service),
) -> VoiceSynthesisResponse:
    """Generate Piper audio after response text has already reached the user."""
    user_id = str(current_user.get("sub") or "")
    source = await run_in_threadpool(
        VoiceRepository.get_synthesis_source,
        request.response_message_id,
        user_id,
    )
    if not source:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error_code": "VOICE_RESPONSE_NOT_FOUND",
                "message": "The voice response was not found for this user.",
            },
        )
    existing_audio_id = source.get("audio_id")
    if existing_audio_id and PiperTextToSpeechService.resolve_audio(existing_audio_id):
        return VoiceSynthesisResponse(
            audio_url=f"/copilot/voice/audio/{existing_audio_id}",
            synthesis_ms=0,
        )
    language = str(source["language"])
    if not speech_output.supports(language):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error_code": "VOICE_OUTPUT_UNSUPPORTED",
                "message": f"Spoken output is not configured for '{language}'.",
            },
        )
    started = time.perf_counter()
    try:
        audio_id = await speech_output.synthesize(str(source["response_text"]), language)
    except TextToSpeechError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"error_code": "VOICE_SYNTHESIS_FAILED", "message": str(exc)},
        ) from exc
    synthesis_ms = round((time.perf_counter() - started) * 1000)
    await run_in_threadpool(
        VoiceRepository.attach_audio,
        request.response_message_id,
        user_id,
        audio_id,
        synthesis_ms,
    )
    return VoiceSynthesisResponse(
        audio_url=f"/copilot/voice/audio/{audio_id}",
        synthesis_ms=synthesis_ms,
    )


@router.get(
    "/voice/audio/{audio_id}",
    summary="Stream generated voice audio",
    dependencies=[Depends(require_role("employee", "admin", "manager"))],
)
async def get_voice_audio(
    audio_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> FileResponse:
    user_id = str(current_user.get("sub") or "")
    authorized = await run_in_threadpool(
        VoiceRepository.audio_belongs_to_user, audio_id, user_id
    )
    path = PiperTextToSpeechService.resolve_audio(audio_id) if authorized else None
    if not path:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error_code": "VOICE_AUDIO_NOT_FOUND",
                "message": "Voice audio was not found or has expired.",
            },
        )
    return FileResponse(
        path,
        media_type="audio/wav",
        filename=f"workmate-{audio_id}.wav",
        headers={"Cache-Control": "private, max-age=300"},
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
    confirmation_response = WorkflowIntentService.confirmation_response(payload.message)
    confirmation_information_request = (
        WorkflowIntentService.is_confirmation_information_request(payload.message)
    )
    prior_history = (
        [
            item
            for item in ConversationRepository.get_history(conversation_id, limit=8)
            if str(item.get("id")) != user_message_id
        ]
        if confirmation_response is not None or confirmation_information_request
        else []
    )
    pending_confirmation = next(
        (
            item
            for item in reversed(prior_history)
            if str(item.get("sender") or "").lower() == "ai"
            and str(item.get("intent") or "").startswith("SOP_CONFIRM:")
        ),
        None,
    )

    # Catalog selection is deterministic and remains available when embeddings
    # or the local model are slow. Only one unambiguous published match can run.
    requested_sop_index = _requested_sop_index(payload.message)
    catalog: list[Dict[str, Any]] = []
    should_check_catalog = bool(
        (confirmation_response is not None and pending_confirmation)
        or payload.selected_workflow_code
        or requested_sop_index is not None
        or WorkflowIntentService.is_workflow_request(payload.message)
        or active_session is None
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

    if pending_confirmation and (
        confirmation_response is not None or confirmation_information_request
    ):
        pending_parts = str(pending_confirmation["intent"]).split(":")
        pending_version_id = pending_parts[1]
        is_memory_confirmation = len(pending_parts) > 3 and pending_parts[2] == "MEMORY"
        pending_resolution_id = pending_parts[3] if is_memory_confirmation else None
        pending_language = pending_parts[4] if len(pending_parts) > 4 else None
        pending_state_id = (
            pending_parts[2]
            if len(pending_parts) > 2 and not is_memory_confirmation
            else None
        )
        pending_match = next(
            (
                item
                for item in catalog
                if str(item.get("workflow_version_id")) == pending_version_id
            ),
            None,
        )
        if confirmation_information_request and pending_match:
            description = str(pending_match.get("description") or "").strip().rstrip(".")
            coverage = _naturalize_sop_coverage(
                description or "the verified operational steps for this process"
            )
            answer = (
                f"This procedure covers {coverage}. "
                "Does that match what you need? Reply yes to use it, or no and "
                "describe what is different."
            )
            answer = await _localized_text(answer, pending_language)
            return _persist_control_reply(
                conversation_id=conversation_id,
                user_message_id=user_message_id,
                intent="WORKFLOW_CONFIRMATION_EXPLAINED",
                answer=answer,
                spoken_answer=answer,
                sop_details=(
                    f"SOP: {pending_match['title']} | "
                    f"{pending_match['workflow_code']}"
                ),
                active_session=active_session,
                position=(
                    WorkflowStateService.get_position(active_session)
                    if active_session
                    else None
                ),
                message_intent=str(pending_confirmation["intent"]),
            )
        if confirmation_response is False:
            if pending_resolution_id:
                try:
                    QueryResolutionRepository.set_status(pending_resolution_id, "REJECTED")
                    QueryResolutionMemoryService.invalidate(department_id)
                except Exception:
                    copilot_logger.exception("Could not reject pending query resolution")
            rejection_answer = (
                "Okay—I won’t start that SOP. Tell me the process, equipment, "
                "or problem you mean, and I’ll find the closest verified workflow."
            )
            rejection_answer = await _localized_text(rejection_answer, pending_language)
            return _persist_control_reply(
                conversation_id=conversation_id,
                user_message_id=user_message_id,
                intent="WORKFLOW_CONFIRMATION_REJECTED",
                answer=rejection_answer,
                spoken_answer=rejection_answer,
                active_session=active_session,
                position=WorkflowStateService.get_position(active_session) if active_session else None,
            )
        if pending_match and not active_session:
            start_kwargs = {
                "conversation_id": conversation_id,
                "workflow_version_id": pending_version_id,
                "user_id": user_id,
            }
            if pending_state_id:
                start_kwargs["start_state_id"] = pending_state_id
            active_session = WorkflowStateService.start_session(**start_kwargs)
            position = WorkflowStateService.get_position(active_session)
            answer = f"Confirmed. Using {pending_match['title']}. {_step_guidance(position)}"
            if pending_resolution_id:
                try:
                    QueryResolutionRepository.set_status(pending_resolution_id, "CONFIRMED")
                    QueryResolutionMemoryService.invalidate(department_id)
                except Exception:
                    copilot_logger.exception("Could not confirm pending query resolution")
            answer = await _localized_text(answer, pending_language)
            return _persist_control_reply(
                conversation_id=conversation_id,
                user_message_id=user_message_id,
                intent="WORKFLOW_START_CONFIRMED",
                answer=answer,
                spoken_answer=answer,
                sop_details=f"SOP: {pending_match['title']} | {pending_match['workflow_code']}",
                active_session=active_session,
                position=position,
            )

    if payload.selected_workflow_code:
        selected_match = next(
            (
                item
                for item in catalog
                if str(item.get("workflow_code") or "").casefold()
                == payload.selected_workflow_code.casefold()
            ),
            None,
        )
        if selected_match is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "error_code": "SOP_SELECTION_INVALID",
                    "message": "That SOP is not published for your department.",
                },
            )
        resolution_id = _create_pending_resolution(
            payload=payload,
            workflow=selected_match,
            department_id=department_id,
            conversation_id=conversation_id,
            user_message_id=user_message_id,
            user_id=user_id,
        )
        answer = _workflow_confirmation_explanation(payload.message, selected_match)
        answer = await _localized_text(answer, payload.response_language)
        confirmation_intent = f"SOP_CONFIRM:{selected_match['workflow_version_id']}"
        if resolution_id:
            confirmation_intent += f":MEMORY:{resolution_id}:{payload.response_language or 'en'}"
        return _persist_control_reply(
            conversation_id=conversation_id,
            user_message_id=user_message_id,
            intent="WORKFLOW_CONFIRMATION_REQUIRED",
            answer=answer,
            spoken_answer=answer,
            sop_details=(
                f"SOP: {selected_match['title']} | {selected_match['workflow_code']}"
            ),
            active_session=active_session,
            position=None,
            message_intent=confirmation_intent,
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

    explicit_workflow_request = WorkflowIntentService.is_workflow_request(payload.message)
    workflow_match = WorkflowIntentService.match_published_workflow(
        payload.message, catalog
    )
    if not workflow_match and active_session is None:
        try:
            workflow_match = QueryResolutionMemoryService.match(
                payload.message, department_id, catalog
            )
        except Exception:
            copilot_logger.exception(
                "Query resolution memory lookup failed; using catalog ranking"
            )
        # Natural questions often contain request verbs ("need", "show") even
        # when they describe a concrete problem. Proposal mode is confirmation-
        # gated, so it is safe to use for both named requests and situations.
        if not workflow_match:
            workflow_match = WorkflowIntentService.match_published_workflow(
                payload.message, catalog, proposal_mode=True
            )
        if not workflow_match:
            ranked_options = WorkflowIntentService.rank_published_workflows(
                payload.message, catalog, limit=3
            )
            # When speech/translation is too noisy for word overlap, still let
            # the employee choose from real published SOPs instead of waiting
            # through model and embedding timeouts or inventing guidance.
            menu_options = ranked_options or catalog[:3]
            if menu_options:
                suggestions = [
                    SopSuggestion(
                        workflow_code=str(item.get("workflow_code") or ""),
                        title=str(item.get("title") or "Published SOP"),
                        description=str(item.get("description") or "").strip(),
                        match_score=float(item.get("match_score") or 0.0),
                        source_query=payload.message,
                    )
                    for item in menu_options
                ]
                if ranked_options:
                    answer = (
                        "I understood part of your request, but more than one verified "
                        "SOP may fit. Choose the closest option below."
                    )
                else:
                    answer = (
                        "I could not confidently match every word. Choose the closest "
                        "published SOP below, or describe the item and problem in another way."
                    )
                top_score = max((item.match_score for item in suggestions), default=0.0)
                return _persist_control_reply(
                    conversation_id=conversation_id,
                    user_message_id=user_message_id,
                    intent="WORKFLOW_SUGGESTIONS",
                    answer=answer,
                    spoken_answer=answer,
                    active_session=active_session,
                    position=None,
                    sop_suggestions=suggestions,
                    confidence_score=max(0.45, min(0.79, top_score)),
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
                answer = _workflow_confirmation_explanation(
                    payload.message, workflow_match
                )
                intent = "WORKFLOW_CONFIRMATION_REQUIRED"
                position = None
            else:
                intent = "WORKFLOW_RESUME"
                position = WorkflowStateService.get_position(active_session)
                answer = _step_guidance(position)
        copilot_logger.info(
            "Resolved workflow catalog intent '%s' with score %.3f",
            intent,
            float(workflow_match.get("match_score") or 0.0),
        )
        resolution_id = (
            _create_pending_resolution(
                payload=payload,
                workflow=workflow_match,
                department_id=department_id,
                conversation_id=conversation_id,
                user_message_id=user_message_id,
                user_id=user_id,
            )
            if intent == "WORKFLOW_CONFIRMATION_REQUIRED"
            else None
        )
        confirmation_intent = f"SOP_CONFIRM:{matched_version_id}"
        if resolution_id:
            confirmation_intent += f":MEMORY:{resolution_id}:{payload.response_language or 'en'}"
        return _persist_control_reply(
            conversation_id=conversation_id,
            user_message_id=user_message_id,
            intent=intent,
            answer=answer,
            spoken_answer=answer,
            sop_details=sop_details,
            active_session=active_session,
            position=position,
            message_intent=(
                confirmation_intent
                if intent == "WORKFLOW_CONFIRMATION_REQUIRED"
                else None
            ),
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
            history = [
                item
                for item in ConversationRepository.get_history(
                    conversation_id, limit=settings.COPILOT_HISTORY_LIMIT + 1
                )
                if str(item.get("id")) != user_message_id
            ][-settings.COPILOT_HISTORY_LIMIT :]
            prior_guidance = CopilotReasoningService.last_verified_instruction(history)
            if prior_guidance and prior_guidance["state_id"] != current_position.state_id:
                followup_reply = await _verified_followup_reply(
                    message=payload.message,
                    prior_state_id=prior_guidance["state_id"],
                    conversation_id=conversation_id,
                    user_message_id=user_message_id,
                    department_id=department_id,
                    role=role,
                    active_session=active_session,
                    position=current_position,
                    advance=True,
                )
                if followup_reply:
                    copilot_logger.info(
                        "Applied completion command to adjacent verified guidance state"
                    )
                    return followup_reply
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
    if not history:
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
        source = retrieved_chunks[0]
        workflow_version_id = str(source.get("workflow_version_id") or "")
        state_id = str(source.get("state_id") or "")
        if workflow_version_id and state_id:
            title = str(source.get("document_title") or "this workflow")
            code = str(source.get("workflow_code") or "").strip()
            answer = _workflow_confirmation_explanation(
                payload.message,
                {
                    "title": title,
                    "state_title": source.get("state_title"),
                    "step_title": source.get("step_title"),
                },
            )
            return _persist_control_reply(
                conversation_id=conversation_id,
                user_message_id=user_message_id,
                intent="WORKFLOW_CONFIRMATION_REQUIRED",
                answer=answer,
                spoken_answer=answer,
                sop_details=f"SOP: {title}{f' | {code}' if code else ''}",
                message_intent=f"SOP_CONFIRM:{workflow_version_id}:{state_id}",
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
