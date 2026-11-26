"""Private, local speech: transcription (faster-whisper), speech synthesis (Piper) and Hindi translation (local Ollama).

Nothing here calls an external service. Audio is processed in memory: it is never written to disk or stored, and the
transcript is returned to the caller for review - it is not saved or sent to the assistant until the employee sends it.
"""
from __future__ import annotations

import asyncio
import io
import json
import logging
import re
import shutil
import subprocess
import wave
from pathlib import Path
from threading import Lock
from typing import Any, Dict, Optional

import numpy as np
from starlette.concurrency import run_in_threadpool

from app.core.config import settings

logger = logging.getLogger("workmate.voice")
SAMPLE_RATE = 16_000
SUPPORTED = ("en", "hi")
DOMAIN_PROMPT = (
    "Warehouse operations: goods receipt, pallet, SKU, scanner, WMS, dock, picking, packing, cycle count, "
    "putaway, damaged cartons, SOP, supervisor."
)


class VoiceError(RuntimeError):
    """Raised with a message that is safe to show to the employee."""

    def __init__(self, message: str, code: str = "VOICE_ERROR", status: int = 400):
        super().__init__(message)
        self.code, self.status = code, status


def _ffmpeg() -> str:
    found = shutil.which(settings.FFMPEG_BIN)
    if not found:
        raise VoiceError("Voice input is not available on this server (audio converter missing).", "VOICE_NO_FFMPEG", 503)
    return found


def decode_to_pcm(data: bytes) -> np.ndarray:
    """Any browser recording (webm/opus, ogg, mp4/aac, wav) -> mono 16 kHz float32, via ffmpeg on stdin/stdout."""
    if not data:
        raise VoiceError("The recording was empty. Please try again.", "VOICE_EMPTY")
    if len(data) > settings.VOICE_MAX_AUDIO_BYTES:
        raise VoiceError("That recording is too large. Keep it under a minute.", "VOICE_TOO_LARGE", 413)
    try:
        proc = subprocess.run(
            [_ffmpeg(), "-hide_banner", "-loglevel", "error", "-i", "pipe:0", "-t", str(settings.VOICE_MAX_SECONDS),
             "-vn", "-ac", "1", "-ar", str(SAMPLE_RATE), "-f", "f32le", "pipe:1"],
            input=data, capture_output=True, timeout=60, check=False)
    except subprocess.TimeoutExpired as exc:
        raise VoiceError("The recording took too long to process.", "VOICE_TIMEOUT", 504) from exc
    if proc.returncode != 0 or not proc.stdout:
        raise VoiceError("That file is not a playable audio recording.", "VOICE_BAD_AUDIO", 415)
    return np.frombuffer(proc.stdout, dtype=np.float32)


class _Whisper:
    """English uses the fast model; Hindi/auto use the larger one (the small model is the smallest that writes Hindi reliably:
    measured here, 'base' answered a Hindi recording with an English paraphrase)."""

    def __init__(self) -> None:
        self._models: Dict[str, Any] = {}
        self._lock = Lock()

    def model(self, name: str) -> Any:
        if name not in self._models:
            with self._lock:
                if name not in self._models:
                    try:
                        from faster_whisper import WhisperModel
                    except Exception as exc:  # pragma: no cover - depends on image
                        raise VoiceError("Speech recognition is not installed on this server.", "VOICE_NO_STT", 503) from exc
                    self._models[name] = WhisperModel(
                        name, device="cpu", compute_type="int8", cpu_threads=settings.WHISPER_CPU_THREADS,
                        download_root=str(Path(settings.WHISPER_DOWNLOAD_ROOT)), local_files_only=settings.WHISPER_LOCAL_ONLY)
        return self._models[name]

    def run(self, audio: np.ndarray, language: Optional[str]) -> Dict[str, Any]:
        name = settings.WHISPER_MODEL_EN if language == "en" else settings.WHISPER_MODEL
        # The English vocabulary hint would push Hindi output into Latin letters, so only English gets it.
        prompt = DOMAIN_PROMPT if language == "en" else None
        segments, info = self.model(name).transcribe(
            audio, language=language, beam_size=1, vad_filter=True, initial_prompt=prompt, condition_on_previous_text=False)
        text = " ".join(s.text.strip() for s in segments).strip()
        return {"text": text, "language": info.language, "probability": round(float(info.language_probability), 2),
                "seconds": round(len(audio) / SAMPLE_RATE, 1), "model": name}


_whisper = _Whisper()
_infer_lock = Lock()  # one transcription at a time: protects a small CPU host from piling up


async def transcribe(data: bytes, language: str = "auto") -> Dict[str, Any]:
    audio = await run_in_threadpool(decode_to_pcm, data)
    if len(audio) < SAMPLE_RATE * 0.4:
        raise VoiceError("I could not hear anything. Tap the microphone and speak for a moment.", "VOICE_TOO_SHORT")
    forced = language if language in SUPPORTED else None

    def work() -> Dict[str, Any]:
        with _infer_lock:
            return _whisper.run(audio, forced)

    result = await run_in_threadpool(work)
    if not result["text"]:
        raise VoiceError("I could not make out any words. Please try again, closer to the microphone.", "VOICE_NO_SPEECH")
    return result


class _Piper:
    def __init__(self) -> None:
        self._voices: Dict[str, Any] = {}
        self._lock = Lock()

    def voice_map(self) -> Dict[str, str]:
        try:
            raw = json.loads(settings.PIPER_VOICE_MAP)
            return {str(k): str(v) for k, v in raw.items()}
        except (json.JSONDecodeError, AttributeError):
            return {}

    def available(self) -> Dict[str, bool]:
        base = Path(settings.PIPER_VOICE_DIR)
        return {lang: (base / f"{name}.onnx").is_file() and (base / f"{name}.onnx.json").is_file()
                for lang, name in self.voice_map().items()}

    def wav(self, text: str, language: str) -> bytes:
        name = self.voice_map().get(language)
        if not name or not self.available().get(language):
            raise VoiceError("A voice for that language is not installed on this server.", "VOICE_NO_TTS", 503)
        with self._lock:
            if language not in self._voices:
                from piper import PiperVoice
                self._voices[language] = PiperVoice.load(str(Path(settings.PIPER_VOICE_DIR) / f"{name}.onnx"))
            voice = self._voices[language]
            buffer = io.BytesIO()
            with wave.open(buffer, "wb") as out:
                try:
                    voice.synthesize_wav(text, out)
                except wave.Error as exc:
                    raise VoiceError("There is nothing I can read aloud in that text.", "VOICE_NO_TEXT") from exc
        return buffer.getvalue()


_piper = _Piper()


def _speakable(text: str) -> str:
    """Strip markdown/citation noise so the voice reads sentences, not symbols."""
    text = re.sub(r"\[[^\]]{0,40}\]", " ", text)
    text = re.sub(r"[*_`#>|]+", " ", text)
    text = re.sub(r"^\s*(\d+)[.)]\s+", r"Step \1. ", text, flags=re.MULTILINE)
    return re.sub(r"\s+", " ", text).strip()


async def synthesize(text: str, language: str) -> bytes:
    if language not in SUPPORTED:
        raise VoiceError("Speech is available in English and Hindi.", "VOICE_LANGUAGE")
    spoken = _speakable(text)[: settings.VOICE_MAX_TTS_CHARS]
    if not spoken:
        raise VoiceError("There is nothing to read aloud.", "VOICE_NO_TEXT")
    return await run_in_threadpool(_piper.wav, spoken, language)


_DEVANAGARI = re.compile(r"[ऀ-ॿ]")
_NUMBER = re.compile(r"\b\d+(?:[.,]\d+)?\b")
_CODE = re.compile(r"\b[A-Z]{2,}[-_][A-Z0-9_-]+\b")
# Warehouse nouns the general-purpose translator gets wrong (measured: "cartons" -> "cards", "rack" -> "rope").
# They are swapped for the Hindi words floor staff actually use BEFORE translation.
GLOSSARY = {
    "cartons": "कार्टन", "carton": "कार्टन", "boxes": "बॉक्स", "box": "बॉक्स", "pallets": "पैलेट", "pallet": "पैलेट",
    "racks": "रैक", "rack": "रैक", "forklift": "फोर्कलिफ्ट", "scanner": "स्कैनर", "supervisor": "सुपरवाइज़र",
    "stock": "स्टॉक", "dock": "डॉक", "shipment": "शिपमेंट", "label": "लेबल", "labels": "लेबल", "receipt": "रसीद",
    "barcode": "बारकोड", "trolley": "ट्रॉली", "aisle": "गलियारा", "bin": "बिन",
}
_GLOSSARY_RE = re.compile(r"\b(" + "|".join(sorted(GLOSSARY, key=len, reverse=True)) + r")\b", re.IGNORECASE)


class _Translator:
    """M2M100 (MIT licence) through CTranslate2, int8 on CPU. Loaded on first use."""

    def __init__(self) -> None:
        self._tr: Any = None
        self._sp: Any = None
        self._lock = Lock()

    def load(self) -> None:
        if self._tr is not None:
            return
        with self._lock:
            if self._tr is None:
                folder = Path(settings.HINDI_TRANSLATION_MODEL_DIR)
                if not (folder / "model.bin").is_file():
                    raise VoiceError("Hindi translation is not installed on this server.", "VOICE_NO_TRANSLATOR", 503)
                import ctranslate2
                import sentencepiece
                sp = sentencepiece.SentencePieceProcessor()
                sp.load(str(folder / "sentencepiece.bpe.model"))
                self._sp = sp
                self._tr = ctranslate2.Translator(str(folder), device="cpu", compute_type="int8", inter_threads=1,
                                                  intra_threads=settings.WHISPER_CPU_THREADS)

    def run(self, text: str) -> str:
        self.load()
        pieces = ["__en__"] + self._sp.encode(text, out_type=str)[:400] + ["</s>"]
        result = self._tr.translate_batch([pieces], target_prefix=[["__hi__"]], beam_size=2, max_decoding_length=320)
        return self._sp.decode(result[0].hypotheses[0][1:]).strip()


_translator = _Translator()
_translate_lock = Lock()


def _sentences(text: str) -> list:
    out = []
    for line in re.split(r"[\r\n]+", text):
        line = line.strip()
        if line:
            out.extend(p for p in re.split(r"(?<=[.!?])\s+", line) if p.strip())
    return out[:40]


def _translate_blocking(text: str) -> str:
    cleaned = _CODE.sub("", re.sub(r"\[[^\]]{0,40}\]", " ", text))
    cleaned = _GLOSSARY_RE.sub(lambda m: GLOSSARY[m.group(1).lower()], cleaned)
    parts = []
    with _translate_lock:
        for sentence in _sentences(cleaned):
            parts.append(_translator.run(sentence))
    return " ".join(p for p in parts if p)


async def translate_to_hindi(text: str) -> str:
    """Machine-translate an approved answer to Hindi. A translation that changes a number is discarded, never shown."""
    try:
        hindi = await run_in_threadpool(_translate_blocking, text)
    except VoiceError:
        raise
    except Exception as exc:
        logger.warning("Hindi translation failed: %s", type(exc).__name__)
        raise VoiceError("Hindi translation is unavailable right now. The English answer is still correct.",
                         "VOICE_TRANSLATE_FAILED", 503) from exc
    if len(_DEVANAGARI.findall(hindi)) < 5:
        raise VoiceError("I could not produce a reliable Hindi version. Please read the English answer.",
                         "VOICE_TRANSLATE_REJECTED", 502)
    ascii_hindi = hindi.translate(str.maketrans("०१२३४५६७८९", "0123456789"))
    if any(n not in ascii_hindi for n in set(_NUMBER.findall(text))):  # a changed quantity is worse than no translation
        raise VoiceError("I could not translate this safely (a number changed). Please read the English answer.",
                         "VOICE_TRANSLATE_REJECTED", 502)
    return hindi


def prewarm() -> None:
    """Load every model once, in the background. Failures are logged and never stop the API."""
    import time
    started = time.perf_counter()
    steps = (
        ("whisper-" + settings.WHISPER_MODEL_EN, lambda: _whisper.model(settings.WHISPER_MODEL_EN)),
        ("whisper-" + settings.WHISPER_MODEL, lambda: _whisper.model(settings.WHISPER_MODEL)),
        ("piper", lambda: [_piper.wav("ready", lang) for lang in SUPPORTED if _piper.available().get(lang)]),
        ("translation", lambda: _translator.load()),
    )
    for name, load in steps:
        try:
            begin = time.perf_counter()
            load()
            logger.info("voice prewarm: %s ready in %.1fs", name, time.perf_counter() - begin)
        except Exception as exc:
            logger.warning("voice prewarm: %s skipped (%s)", name, type(exc).__name__)
    logger.info("voice prewarm finished in %.1fs", time.perf_counter() - started)


def status() -> Dict[str, Any]:
    return {
        "enabled": bool(settings.VOICE_ENABLED),
        "ffmpeg": bool(shutil.which(settings.FFMPEG_BIN)),
        "speech_to_text": {"models": {"en": settings.WHISPER_MODEL_EN, "hi": settings.WHISPER_MODEL}, "languages": list(SUPPORTED)},
        "text_to_speech": _piper.available(),
        "translation": {"hindi": (Path(settings.HINDI_TRANSLATION_MODEL_DIR) / "model.bin").is_file()},
    }
