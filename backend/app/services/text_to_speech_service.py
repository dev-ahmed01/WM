"""Piper-backed local text-to-speech with configurable per-language voices."""

import json
import logging
import time
import uuid
import wave
from functools import lru_cache
from pathlib import Path
from threading import Lock
from typing import Any

from starlette.concurrency import run_in_threadpool

from app.core.config import settings

logger = logging.getLogger("workmate.voice.tts")


class TextToSpeechError(RuntimeError):
    pass


class PiperTextToSpeechService:
    def __init__(self) -> None:
        try:
            raw_map = json.loads(settings.PIPER_VOICE_MAP)
        except json.JSONDecodeError as exc:
            raise TextToSpeechError("PIPER_VOICE_MAP must be valid JSON") from exc
        if not isinstance(raw_map, dict):
            raise TextToSpeechError("PIPER_VOICE_MAP must be a language-to-model object")
        self.voice_map = {str(key): str(value) for key, value in raw_map.items()}
        self._voices: dict[str, Any] = {}
        self._lock = Lock()
        Path(settings.VOICE_AUDIO_DIR).mkdir(parents=True, exist_ok=True)

    def supports(self, language: str) -> bool:
        return language in self.voice_map

    def _get_voice(self, language: str) -> Any:
        if language in self._voices:
            return self._voices[language]
        model_name = self.voice_map.get(language)
        if not model_name:
            raise TextToSpeechError(f"No Piper voice is configured for language '{language}'")
        model_path = Path(settings.PIPER_VOICE_DIR) / model_name
        if not model_path.is_file() or not Path(f"{model_path}.json").is_file():
            raise TextToSpeechError(
                f"Piper voice files are missing for language '{language}'"
            )
        with self._lock:
            if language not in self._voices:
                from piper import PiperVoice

                self._voices[language] = PiperVoice.load(
                    str(model_path), use_cuda=settings.PIPER_USE_CUDA
                )
        return self._voices[language]

    def _cleanup_expired(self) -> None:
        cutoff = time.time() - settings.VOICE_AUDIO_TTL_SECONDS
        for path in Path(settings.VOICE_AUDIO_DIR).glob("voice_*.wav"):
            try:
                if path.stat().st_mtime < cutoff:
                    path.unlink()
            except OSError:
                logger.warning("Unable to remove expired voice audio '%s'", path)

    def _synthesize_sync(self, text: str, language: str) -> str:
        if not text.strip():
            raise TextToSpeechError("Cannot synthesize empty text")
        voice = self._get_voice(language)
        self._cleanup_expired()
        audio_id = f"voice_{uuid.uuid4().hex}"
        output_path = Path(settings.VOICE_AUDIO_DIR) / f"{audio_id}.wav"
        try:
            with wave.open(str(output_path), "wb") as wav_file:
                voice.synthesize_wav(text, wav_file)
        except Exception as exc:
            output_path.unlink(missing_ok=True)
            raise TextToSpeechError("Piper speech synthesis failed") from exc
        return audio_id

    async def synthesize(self, text: str, language: str) -> str:
        return await run_in_threadpool(self._synthesize_sync, text, language)

    @staticmethod
    def resolve_audio(audio_id: str) -> Path | None:
        if not audio_id.startswith("voice_") or not audio_id[6:].isalnum():
            return None
        path = Path(settings.VOICE_AUDIO_DIR) / f"{audio_id}.wav"
        return path if path.is_file() else None


@lru_cache
def get_text_to_speech_service() -> PiperTextToSpeechService:
    return PiperTextToSpeechService()
