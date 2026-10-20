"""Authenticated multilingual Copilot voice endpoint tests."""

import json
from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.copilot import router
from app.core.security import create_access_token
from app.models.copilot import CopilotResponse, SopSuggestion
from app.models.voice import TranscriptionResult
from app.services.speech_recognition_service import get_speech_recognition_service
from app.services.speech_recognition_service import FasterWhisperSpeechRecognitionService
from app.services.text_to_speech_service import get_text_to_speech_service
from app.services.translation_service import get_translation_service


app = FastAPI()
app.include_router(router, prefix="/api/v1")
client = TestClient(app)
TOKEN = create_access_token("usr_emp", "employee", "dept_ops")

@pytest.fixture(autouse=True)
def no_current_workflow_for_voice_unit_tests(monkeypatch):
    # Each voice route remains hermetic; explicit workflow-context checks are
    # tested separately without accidentally opening a real PostgreSQL pool.
    monkeypatch.setattr("app.api.v1.copilot.WorkflowStateService.get_current_session", lambda _: None)



class FakeSpeechRecognition:
    async def transcribe(self, _path: Path, requested_language: str | None = None):
        assert requested_language is None
        return TranscriptionResult(
            transcript="पैकेज क्षतिग्रस्त है", language="hi", confidence=0.96
        )


class FakeTranslation:
    async def translate_to_english(self, text: str, source_language: str):
        assert (text, source_language) == ("पैकेज क्षतिग्रस्त है", "hi")
        return "The package is damaged"

    async def translate_from_english(self, text: str, target_language: str):
        assert target_language == "hi"
        assert text == "Use the verified damage procedure."
        return "सत्यापित क्षति प्रक्रिया का उपयोग करें।"


class FakeSpeechOutput:
    def supports(self, language: str) -> bool:
        return language == "hi"

    async def synthesize(self, text: str, language: str) -> str:
        assert (text, language) == ("सत्यापित क्षति प्रक्रिया का उपयोग करें।", "hi")
        return "voice_test123"


def copilot_result() -> CopilotResponse:
    return CopilotResponse(
        conversation_id="conv_voice",
        message_id="msg_ai",
        answer="Use the verified damage procedure.",
        citations=[],
        confidence_score=1.0,
        is_grounded=True,
        requires_escalation=False,
    )


def test_hindi_voice_flow_translates_calls_copilot_and_returns_audio_url():
    app.dependency_overrides[get_speech_recognition_service] = FakeSpeechRecognition
    app.dependency_overrides[get_translation_service] = FakeTranslation
    app.dependency_overrides[get_text_to_speech_service] = FakeSpeechOutput
    try:
        with (
            patch(
                "app.api.v1.copilot.ConversationRepository.get_or_create_session",
                return_value="conv_voice",
            ),
            patch(
                "app.api.v1.copilot.copilot_message",
                new_callable=AsyncMock,
                return_value=copilot_result(),
            ) as copilot,
            patch(
                "app.api.v1.copilot.VoiceRepository.persist_interaction",
                return_value="voice_row",
            ) as persist,
            patch("app.api.v1.copilot.AnalyticsService.record_event"),
        ):
            response = client.post(
                "/api/v1/copilot/voice",
                headers={"Authorization": f"Bearer {TOKEN}"},
                data={"language": "auto", "synthesize": "true"},
                files={"audio": ("voice.webm", b"audio bytes", "audio/webm")},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["language"] == "hi"
    assert body["transcript"] == "पैकेज क्षतिग्रस्त है"
    assert body["translated_transcript"] == "The package is damaged"
    assert body["response_text"] == "सत्यापित क्षति प्रक्रिया का उपयोग करें।"
    assert body["audio_url"] == "/copilot/voice/audio/voice_test123"
    assert body["confidence"] == 0.96
    assert body["copilot"]["answer"] == body["response_text"]
    assert copilot.await_args.args[0].message == "The package is damaged"
    assert persist.call_args.kwargs["original_language"] == "hi"
    assert persist.call_args.kwargs["translated_language"] == "en"
    assert persist.call_args.kwargs["success"] is True


def test_voice_can_return_text_before_audio_is_synthesized():
    class DeferredSpeechOutput:
        def supports(self, _language: str) -> bool:
            return True

        async def synthesize(self, _text: str, _language: str) -> str:
            raise AssertionError("synthesis must be deferred")

    app.dependency_overrides[get_speech_recognition_service] = FakeSpeechRecognition
    app.dependency_overrides[get_translation_service] = FakeTranslation
    app.dependency_overrides[get_text_to_speech_service] = DeferredSpeechOutput
    try:
        with (
            patch(
                "app.api.v1.copilot.ConversationRepository.get_or_create_session",
                return_value="conv_voice",
            ),
            patch(
                "app.api.v1.copilot.copilot_message",
                new_callable=AsyncMock,
                return_value=copilot_result(),
            ),
            patch(
                "app.api.v1.copilot.VoiceRepository.persist_interaction",
                return_value="voice_row",
            ) as persist,
            patch("app.api.v1.copilot.AnalyticsService.record_event"),
        ):
            response = client.post(
                "/api/v1/copilot/voice",
                headers={"Authorization": f"Bearer {TOKEN}"},
                data={"language": "auto", "synthesize": "false"},
                files={"audio": ("voice.webm", b"audio bytes", "audio/webm")},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["audio_url"] is None
    assert response.json()["synthesis_ms"] == 0
    assert persist.call_args.kwargs["audio_id"] is None


def test_hindi_voice_localizes_sop_suggestion_menu_in_one_batch():
    class MenuTranslation(FakeTranslation):
        async def translate_many_from_english(self, texts, target_language):
            assert target_language == "hi"
            assert texts == [
                "Choose the closest verified SOP.",
                "Damage Inspection",
                "Inspect damaged goods before stocking.",
            ]
            return [
                "निकटतम सत्यापित प्रक्रिया चुनें।",
                "क्षति निरीक्षण",
                "भंडारण से पहले क्षतिग्रस्त सामान की जाँच करें।",
            ]

    result = copilot_result().model_copy(
        update={
            "answer": "Choose the closest verified SOP.",
            "sop_suggestions": [
                SopSuggestion(
                    workflow_code="WH_REC_003",
                    title="Damage Inspection",
                    description="Inspect damaged goods before stocking.",
                    match_score=0.9,
                )
            ],
        }
    )
    app.dependency_overrides[get_speech_recognition_service] = FakeSpeechRecognition
    app.dependency_overrides[get_translation_service] = MenuTranslation
    app.dependency_overrides[get_text_to_speech_service] = FakeSpeechOutput
    try:
        with (
            patch(
                "app.api.v1.copilot.ConversationRepository.get_or_create_session",
                return_value="conv_voice",
            ),
            patch(
                "app.api.v1.copilot.copilot_message",
                new_callable=AsyncMock,
                return_value=result,
            ),
            patch("app.api.v1.copilot.VoiceRepository.persist_interaction"),
            patch("app.api.v1.copilot.AnalyticsService.record_event"),
        ):
            response = client.post(
                "/api/v1/copilot/voice",
                headers={"Authorization": f"Bearer {TOKEN}"},
                data={"language": "auto", "synthesize": "false"},
                files={"audio": ("voice.webm", b"audio bytes", "audio/webm")},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    suggestion = response.json()["copilot"]["sop_suggestions"][0]
    assert suggestion["title"] == "क्षति निरीक्षण"
    assert suggestion["description"].startswith("भंडारण से पहले")
    assert suggestion["workflow_code"] == "WH_REC_003"


def test_deferred_speech_is_authorized_and_attached_to_interaction():
    app.dependency_overrides[get_text_to_speech_service] = FakeSpeechOutput
    try:
        with (
            patch(
                "app.api.v1.copilot.VoiceRepository.get_synthesis_source",
                return_value={
                    "response_text": "सत्यापित क्षति प्रक्रिया का उपयोग करें।",
                    "language": "hi",
                    "audio_id": None,
                },
            ),
            patch("app.api.v1.copilot.VoiceRepository.attach_audio") as attach,
        ):
            response = client.post(
                "/api/v1/copilot/voice/speech",
                headers={"Authorization": f"Bearer {TOKEN}"},
                json={"response_message_id": "msg_ai"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["audio_url"] == "/copilot/voice/audio/voice_test123"
    assert response.json()["synthesis_ms"] >= 0
    assert attach.call_args.args[:3] == ("msg_ai", "usr_emp", "voice_test123")


def test_voice_endpoint_rejects_unsupported_media_before_transcription():
    response = client.post(
        "/api/v1/copilot/voice",
        headers={"Authorization": f"Bearer {TOKEN}"},
        files={"audio": ("notes.txt", b"not audio", "text/plain")},
    )
    assert response.status_code == 415
    assert response.json()["detail"]["error_code"] == "VOICE_AUDIO_TYPE_UNSUPPORTED"


@pytest.mark.parametrize(
    "content_type",
    ["audio/webm;codecs=opus", "video/webm;codecs=opus"],
)
def test_voice_endpoint_accepts_chrome_webm_codec_content_type(content_type):
    class EmptySpeechRecognition:
        async def transcribe(self, _path: Path, requested_language: str | None = None):
            raise RuntimeError("media type accepted")

    app.dependency_overrides[get_speech_recognition_service] = EmptySpeechRecognition
    try:
        with patch(
            "app.api.v1.copilot.ConversationRepository.get_or_create_session",
            return_value="conv_voice",
        ):
            with pytest.raises(RuntimeError, match="media type accepted"):
                client.post(
                    "/api/v1/copilot/voice",
                    headers={"Authorization": f"Bearer {TOKEN}"},
                    files={
                        "audio": (
                            "voice.webm",
                            b"webm audio",
                            content_type,
                        )
                    },
                )
    finally:
        app.dependency_overrides.clear()


def test_voice_endpoint_requires_supported_language():
    response = client.post(
        "/api/v1/copilot/voice",
        headers={"Authorization": f"Bearer {TOKEN}"},
        data={"language": "fr"},
        files={"audio": ("voice.wav", b"audio", "audio/wav")},
    )
    assert response.status_code == 422
    assert response.json()["detail"]["error_code"] == "VOICE_LANGUAGE_UNSUPPORTED"


def test_detected_unsupported_language_is_persisted_as_failed():
    class UnsupportedSpeechRecognition:
        async def transcribe(self, _path: Path, requested_language: str | None = None):
            return TranscriptionResult(transcript="bonjour", language="fr", confidence=0.91)

    app.dependency_overrides[get_speech_recognition_service] = UnsupportedSpeechRecognition
    try:
        with (
            patch(
                "app.api.v1.copilot.ConversationRepository.get_or_create_session",
                return_value="conv_voice",
            ),
            patch(
                "app.api.v1.copilot.VoiceRepository.persist_interaction",
                return_value="voice_failed",
            ) as persist,
            patch("app.api.v1.copilot.AnalyticsService.record_event"),
        ):
            response = client.post(
                "/api/v1/copilot/voice",
                headers={"Authorization": f"Bearer {TOKEN}"},
                data={"language": "auto"},
                files={"audio": ("voice.wav", b"audio", "audio/wav")},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422
    assert response.json()["detail"]["error_code"] == "VOICE_LANGUAGE_UNSUPPORTED"
    assert persist.call_args.kwargs["original_language"] == "fr"
    assert persist.call_args.kwargs["success"] is False


def test_whisper_uses_medium_when_large_model_exceeds_cgroup_memory(monkeypatch):
    service = FasterWhisperSpeechRecognitionService()
    monkeypatch.setattr(service, "_memory_limit_bytes", lambda: 4 * 1024**3)
    monkeypatch.setattr(
        "app.services.speech_recognition_service.settings.WHISPER_MODEL", "large-v3"
    )
    monkeypatch.setattr(
        "app.services.speech_recognition_service.settings.WHISPER_FALLBACK_MODEL", "medium"
    )
    monkeypatch.setattr(
        "app.services.speech_recognition_service.settings.WHISPER_LARGE_MIN_MEMORY_GB", 6.0
    )

    assert service._candidate_models() == ["medium"]


def test_whisper_uses_isolated_worker_when_memory_is_constrained(monkeypatch):
    service = FasterWhisperSpeechRecognitionService()
    monkeypatch.setattr(service, "_memory_limit_bytes", lambda: 4 * 1024**3)
    monkeypatch.setattr(
        "app.services.speech_recognition_service.settings.VOICE_MODEL_REUSE_MIN_MEMORY_GB",
        8.0,
    )

    assert service._requires_isolated_worker() is True


def test_isolated_whisper_worker_parses_structured_result(monkeypatch, tmp_path):
    result = {
        "transcript": "पैकेज क्षतिग्रस्त है",
        "language": "hi",
        "confidence": 0.94,
    }
    run = patch(
        "app.services.speech_recognition_service.subprocess.run",
        return_value=CompletedProcess([], 0, stdout=json.dumps(result), stderr=""),
    )
    with run as mocked_run:
        parsed = FasterWhisperSpeechRecognitionService._transcribe_isolated_sync(
            tmp_path / "voice.wav", None
        )

    assert parsed.transcript == result["transcript"]
    assert parsed.language == "hi"
    assert mocked_run.call_args.args[0][-1] == "auto"


def test_whisper_reuses_model_on_current_memory_profile(monkeypatch):
    service = FasterWhisperSpeechRecognitionService()
    monkeypatch.setattr(service, "_memory_limit_bytes", lambda: int(3.67 * 1024**3))
    monkeypatch.setattr(
        "app.services.speech_recognition_service.settings.VOICE_MODEL_REUSE_MIN_MEMORY_GB",
        3.5,
    )

    assert service._requires_isolated_worker() is False


def test_compact_voice_defaults_fit_the_constrained_runtime():
    from app.core.config import settings

    assert settings.VOICE_SUPPORTED_LANGUAGES == "en,hi"
    assert settings.WHISPER_MODEL == "base"
    assert settings.WHISPER_FALLBACK_MODEL == "tiny"
    assert settings.WHISPER_BEAM_SIZE == 1
    assert settings.WHISPER_CPU_THREADS == 4
    assert settings.VOICE_MODEL_REUSE_MIN_MEMORY_GB == 3.5
    assert "क्षतिग्रस्त" in settings.WHISPER_HOTWORDS


def test_voice_action_guard_requires_review_for_ambiguous_commands():
    from app.api.v1.copilot import _voice_needs_confirmation
    from types import SimpleNamespace
    for command in ("done", "yes", "next", "jump to step 3", "pause", "complete through step 2"):
        assert _voice_needs_confirmation(command, 0.99, None)
    assert _voice_needs_confirmation("How do I inspect a seal?", 0.35, None)
    assert _voice_needs_confirmation("Where is the receiving station?", 0.99, SimpleNamespace(status="active"))
    assert not _voice_needs_confirmation("Where is the receiving station?", 0.99, None)


def test_unsafe_voice_step_command_returns_editable_transcript_without_execution():
    class SpokenCommand:
        async def transcribe(self, _path, _language=None):
            return TranscriptionResult(transcript="done", language="en", confidence=0.98)
    class IdentityTranslation:
        async def translate_to_english(self, text, _language):
            return text
    app.dependency_overrides[get_speech_recognition_service] = SpokenCommand
    app.dependency_overrides[get_translation_service] = IdentityTranslation
    try:
        with (
            patch("app.api.v1.copilot.ConversationRepository.get_or_create_session", return_value="conv_voice"),
            patch("app.api.v1.copilot.copilot_message", new_callable=AsyncMock) as unsafe_copilot,
            patch("app.api.v1.copilot.VoiceRepository.persist_interaction", return_value="voice_review_row") as persist,
            patch("app.api.v1.copilot.AnalyticsService.record_event"),
        ):
            response = client.post(
                "/api/v1/copilot/voice",
                headers={"Authorization": f"Bearer {TOKEN}"},
                data={"language": "auto"},
                files={"audio": ("voice.webm", b"sample audio", "audio/webm")},
            )
        assert response.status_code == 409
        detail = response.json()["detail"]
        assert detail["error_code"] == "VOICE_CONFIRM_TRANSCRIPT"
        assert detail["details"]["translated_transcript"] == "done"
        assert detail["details"]["conversation_id"] == "conv_voice"
        unsafe_copilot.assert_not_awaited()
        assert persist.call_args.kwargs["success"] is False
    finally:
        app.dependency_overrides.clear()


def test_transcription_preview_never_creates_conversation_or_changes_workflow():
    class EnglishVoice:
        async def transcribe(self, _path, language=None):
            assert language is None
            return TranscriptionResult(
                transcript="Inspect the incoming pallet", language="en", confidence=0.94
            )

    class EnglishTranslation:
        async def translate_to_english(self, text, language):
            assert (text, language) == ("Inspect the incoming pallet", "en")
            return text

    app.dependency_overrides[get_speech_recognition_service] = EnglishVoice
    app.dependency_overrides[get_translation_service] = EnglishTranslation
    try:
        with (
            patch("app.api.v1.copilot.ConversationRepository.get_or_create_session") as conversation,
            patch("app.api.v1.copilot.copilot_message", new_callable=AsyncMock) as copilot,
            patch("app.api.v1.copilot.WorkflowStateService.get_current_session") as workflow,
            patch("app.api.v1.copilot.VoiceRepository.persist_interaction") as audit,
        ):
            response = client.post(
                "/api/v1/copilot/voice/transcribe",
                headers={"Authorization": f"Bearer {TOKEN}"},
                data={"language": "auto"},
                files={"audio": ("voice.webm", b"audio bytes", "audio/webm")},
            )
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["transcript"] == "Inspect the incoming pallet"
        assert data["suggested_text"] == data["transcript"]
        assert data["detected_language"] == "en"
        assert data["requires_confirmation"] is True
        conversation.assert_not_called()
        workflow.assert_not_called()
        copilot.assert_not_awaited()
        audit.assert_not_called()
    finally:
        app.dependency_overrides.clear()


def test_hinglish_devanagari_preview_translates_without_workflow_mutation():
    class HinglishVoice:
        async def transcribe(self, _path, _requested=None):
            return TranscriptionResult(
                transcript="Barcode को scan करो", language="en", confidence=0.55,
            )
    class HinglishTranslation:
        async def translate_to_english(self, text, language):
            assert language == "hi"  # Script evidence corrects auto-detection.
            assert text == "Barcode को scan करो"
            return "Scan the barcode"

    app.dependency_overrides[get_speech_recognition_service] = HinglishVoice
    app.dependency_overrides[get_translation_service] = HinglishTranslation
    try:
        with patch("app.api.v1.copilot.copilot_message", new_callable=AsyncMock) as copilot:
            response = client.post(
                "/api/v1/copilot/voice/transcribe",
                headers={"Authorization": f"Bearer {TOKEN}"},
                files={"audio": ("voice.webm", b"audio bytes", "audio/webm")},
            )
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["detected_language"] == "hi"
        assert data["confidence"] == 0.55
        assert data["suggested_text"] == "Scan the barcode"
        assert data["requires_confirmation"] is True
        copilot.assert_not_awaited()
    finally:
        app.dependency_overrides.clear()


def test_transcription_preview_requires_authentication():
    response = client.post(
        "/api/v1/copilot/voice/transcribe",
        files={"audio": ("voice.webm", b"audio bytes", "audio/webm")},
    )
    assert response.status_code in {401, 403}


def test_transcription_preview_rejects_wrong_media_before_model():
    response = client.post(
        "/api/v1/copilot/voice/transcribe",
        headers={"Authorization": f"Bearer {TOKEN}"},
        files={"audio": ("voice.exe", b"malformed", "application/x-msdownload")},
    )
    assert response.status_code == 415


def test_task_voice_preview_rejects_oversized_audio_before_asr_or_any_write(monkeypatch):
    """Enforce actual upload bounds even when a MIME type looks legitimate."""
    from app.api.v1 import copilot as voice_api

    monkeypatch.setattr(voice_api.settings, "VOICE_MAX_AUDIO_BYTES", 8)
    with (
        patch("app.api.v1.copilot.ConversationRepository.get_or_create_session") as conversation,
        patch("app.api.v1.copilot.VoiceRepository.persist_interaction") as audit,
        patch("app.api.v1.copilot.WorkflowStateService.get_current_session") as workflow,
    ):
        response = client.post(
            "/api/v1/copilot/voice/transcribe",
            headers={"Authorization": f"Bearer {TOKEN}"},
            data={"language": "auto"},
            files={"audio": ("voice.webm", b"audio bytes exceed the test limit", "audio/webm")},
        )
    assert response.status_code == 413
    assert response.json()["detail"]["error_code"] == "VOICE_AUDIO_TOO_LARGE"
    conversation.assert_not_called()
    audit.assert_not_called()
    workflow.assert_not_called()


def test_task_voice_preview_does_not_interpret_spoken_step_commands():
    """Even an unambiguous 'skip' is a draft, never a workflow command."""
    class SpokenDangerousCommand:
        async def transcribe(self, _path, language=None):
            assert language == "en"
            return TranscriptionResult(
                transcript="Skip step 9 and release the hold",
                language="en", confidence=0.99,
            )

    class EnglishIdentityTranslation:
        async def translate_to_english(self, text, language):
            assert language == "en"
            return text

    app.dependency_overrides[get_speech_recognition_service] = SpokenDangerousCommand
    app.dependency_overrides[get_translation_service] = EnglishIdentityTranslation
    try:
        with (
            patch("app.api.v1.copilot.ConversationRepository.get_or_create_session") as conversation,
            patch("app.api.v1.copilot.copilot_message", new_callable=AsyncMock) as copilot,
            patch("app.api.v1.copilot.WorkflowStateService.get_current_session") as workflow,
            patch("app.api.v1.copilot.VoiceRepository.persist_interaction") as audit,
        ):
            response = client.post(
                "/api/v1/copilot/voice/transcribe",
                headers={"Authorization": f"Bearer {TOKEN}"},
                data={"language": "en"},
                files={"audio": ("voice.webm", b"audio bytes", "audio/webm;codecs=opus")},
            )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["suggested_text"] == "Skip step 9 and release the hold"
        assert body["requires_confirmation"] is True
        conversation.assert_not_called()
        copilot.assert_not_awaited()
        workflow.assert_not_called()
        audit.assert_not_called()
    finally:
        app.dependency_overrides.clear()


def test_task_voice_preview_rejects_empty_upload():
    response = client.post(
        "/api/v1/copilot/voice/transcribe",
        headers={"Authorization": f"Bearer {TOKEN}"},
        files={"audio": ("voice.webm", b"", "audio/webm")},
    )
    assert response.status_code == 422
    assert response.json()["detail"]["error_code"] == "VOICE_AUDIO_EMPTY"
