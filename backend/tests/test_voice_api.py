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
from app.models.copilot import CopilotResponse
from app.models.voice import TranscriptionResult
from app.services.speech_recognition_service import get_speech_recognition_service
from app.services.speech_recognition_service import FasterWhisperSpeechRecognitionService
from app.services.text_to_speech_service import get_text_to_speech_service
from app.services.translation_service import get_translation_service


app = FastAPI()
app.include_router(router, prefix="/api/v1")
client = TestClient(app)
TOKEN = create_access_token("usr_emp", "employee", "dept_ops")


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
                data={"language": "auto"},
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


def test_translation_timeout_allows_local_model_cold_start():
    from app.core.config import settings

    assert settings.TRANSLATION_TIMEOUT_SECONDS >= 60
