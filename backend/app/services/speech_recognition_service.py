"""Faster-Whisper speech recognition with lazy model fallback and language detection."""

import logging
import math
import gc
import json
import subprocess
import sys
from functools import lru_cache
from pathlib import Path
from threading import Lock
from typing import Any

from starlette.concurrency import run_in_threadpool

from app.core.config import settings
from app.models.voice import TranscriptionResult

logger = logging.getLogger("workmate.voice.stt")


class SpeechRecognitionError(RuntimeError):
    pass


class FasterWhisperSpeechRecognitionService:
    """Thread-safe, lazily loaded Faster-Whisper adapter."""

    def __init__(self) -> None:
        self._model: Any = None
        self._model_name: str | None = None
        self._lock = Lock()
        self._inference_lock = Lock()

    @staticmethod
    def _memory_limit_bytes() -> int | None:
        """Return the lowest visible cgroup/VM memory boundary when available."""
        limits: list[int] = []
        for location in (
            Path("/sys/fs/cgroup/memory.max"),
            Path("/sys/fs/cgroup/memory/memory.limit_in_bytes"),
        ):
            try:
                raw = location.read_text(encoding="utf-8").strip()
                if raw and raw != "max":
                    value = int(raw)
                    # Some cgroup v1 hosts expose a huge sentinel for unlimited.
                    if value < 1 << 60:
                        limits.append(value)
            except (OSError, ValueError):
                continue
        try:
            for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
                if line.startswith("MemTotal:"):
                    limits.append(int(line.split()[1]) * 1024)
                    break
        except (OSError, ValueError, IndexError):
            pass
        return min(limits) if limits else None

    def _candidate_models(self) -> list[str]:
        candidates = list(
            dict.fromkeys([settings.WHISPER_MODEL, settings.WHISPER_FALLBACK_MODEL])
        )
        memory_limit = self._memory_limit_bytes()
        required = int(settings.WHISPER_LARGE_MIN_MEMORY_GB * 1024**3)
        if (
            candidates
            and candidates[0].casefold().startswith("large")
            and memory_limit is not None
            and memory_limit < required
            and len(candidates) > 1
        ):
            logger.warning(
                "Skipping preferred Whisper model '%s': cgroup memory %.2f GB is below "
                "the configured %.2f GB safety threshold; using '%s'",
                candidates[0], memory_limit / 1024**3,
                settings.WHISPER_LARGE_MIN_MEMORY_GB, candidates[1],
            )
            return candidates[1:]
        return candidates

    def _load_model(self) -> Any:
        if self._model is not None:
            return self._model
        with self._lock:
            if self._model is not None:
                return self._model
            from faster_whisper import WhisperModel

            errors: list[str] = []
            for model_name in self._candidate_models():
                try:
                    logger.info("Loading Faster-Whisper model '%s'", model_name)
                    self._model = WhisperModel(
                        model_name,
                        device=settings.WHISPER_DEVICE,
                        compute_type=settings.WHISPER_COMPUTE_TYPE,
                        download_root=settings.WHISPER_DOWNLOAD_ROOT,
                        cpu_threads=settings.WHISPER_CPU_THREADS,
                        num_workers=settings.WHISPER_NUM_WORKERS,
                    )
                    self._model_name = model_name
                    return self._model
                except Exception as exc:
                    errors.append(f"{model_name}: {type(exc).__name__}")
                    logger.exception("Unable to load Faster-Whisper model '%s'", model_name)
            raise SpeechRecognitionError(
                "No configured Faster-Whisper model could be loaded (" + ", ".join(errors) + ")"
            )

    def _transcribe_sync(
        self, audio_path: Path, requested_language: str | None
    ) -> TranscriptionResult:
        with self._inference_lock:
            model = self._load_model()
            try:
                segments, info = model.transcribe(
                    str(audio_path),
                    language=requested_language,
                    beam_size=settings.WHISPER_BEAM_SIZE,
                    vad_filter=True,
                    condition_on_previous_text=False,
                    hotwords=settings.WHISPER_HOTWORDS or None,
                )
                realized_segments = list(segments)
            except Exception as exc:
                raise SpeechRecognitionError("Audio transcription failed") from exc
            finally:
                memory_limit = self._memory_limit_bytes()
                reuse_threshold = int(settings.VOICE_MODEL_REUSE_MIN_MEMORY_GB * 1024**3)
                if memory_limit is not None and memory_limit < reuse_threshold:
                    logger.info(
                        "Releasing Whisper model after transcription on %.2f GB worker",
                        memory_limit / 1024**3,
                    )
                    self._model = None
                    self._model_name = None
                    del model
                    gc.collect()

        transcript = " ".join(
            str(segment.text).strip() for segment in realized_segments if str(segment.text).strip()
        ).strip()
        if not transcript:
            raise SpeechRecognitionError("No speech was detected in the uploaded audio")
        language = str(getattr(info, "language", None) or requested_language or "en")
        language_probability = float(getattr(info, "language_probability", 0.0) or 0.0)
        segment_probabilities = [
            max(0.0, min(math.exp(float(segment.avg_logprob)), 1.0))
            for segment in realized_segments
            if getattr(segment, "avg_logprob", None) is not None
        ]
        acoustic_confidence = (
            sum(segment_probabilities) / len(segment_probabilities)
            if segment_probabilities
            else language_probability
        )
        confidence = max(
            0.0,
            min(
                (language_probability + acoustic_confidence) / 2
                if language_probability
                else acoustic_confidence,
                1.0,
            ),
        )
        logger.info(
            "Transcribed audio with model=%s language=%s confidence=%.3f",
            self._model_name or "released",
            language,
            confidence,
        )
        return TranscriptionResult(
            transcript=transcript, language=language, confidence=confidence
        )

    def _requires_isolated_worker(self) -> bool:
        memory_limit = self._memory_limit_bytes()
        threshold = int(settings.VOICE_MODEL_REUSE_MIN_MEMORY_GB * 1024**3)
        return memory_limit is not None and memory_limit < threshold

    @staticmethod
    def _transcribe_isolated_sync(
        audio_path: Path, requested_language: str | None
    ) -> TranscriptionResult:
        """Run native Whisper allocations in a short-lived process on small workers."""
        command = [
            sys.executable,
            "-m",
            "app.services.speech_recognition_worker",
            str(audio_path),
            requested_language or "auto",
        ]
        try:
            completed = subprocess.run(
                command,
                check=True,
                capture_output=True,
                text=True,
                timeout=settings.WHISPER_TRANSCRIPTION_TIMEOUT_SECONDS,
            )
            payload = json.loads(completed.stdout.strip())
            return TranscriptionResult.model_validate(payload)
        except (subprocess.SubprocessError, json.JSONDecodeError, ValueError) as exc:
            logger.error("Isolated Faster-Whisper worker failed: %s", type(exc).__name__)
            raise SpeechRecognitionError("Audio transcription failed") from exc

    def _transcribe_isolated_serialized_sync(
        self, audio_path: Path, requested_language: str | None
    ) -> TranscriptionResult:
        """Prevent retries from loading multiple memory-heavy workers concurrently."""
        with self._inference_lock:
            return self._transcribe_isolated_sync(audio_path, requested_language)

    async def warm(self) -> None:
        """Load the reusable model before the service accepts voice traffic."""
        if not self._requires_isolated_worker():
            await run_in_threadpool(self._load_model)

    async def transcribe(
        self, audio_path: Path, requested_language: str | None = None
    ) -> TranscriptionResult:
        if self._requires_isolated_worker():
            logger.info("Using isolated Faster-Whisper worker to reclaim native memory")
            return await run_in_threadpool(
                self._transcribe_isolated_serialized_sync, audio_path, requested_language
            )
        return await run_in_threadpool(
            self._transcribe_sync, audio_path, requested_language
        )


@lru_cache
def get_speech_recognition_service() -> FasterWhisperSpeechRecognitionService:
    return FasterWhisperSpeechRecognitionService()
