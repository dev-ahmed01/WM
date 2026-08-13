"""Provider-neutral multilingual translation for the Copilot voice pipeline."""

import re
from functools import lru_cache

from app.integrations.ai_provider import TranslationProvider
from app.integrations.local_ai_provider import OllamaLocalAIProvider

SUPPORTED_LANGUAGES = frozenset({"en", "hi", "kn", "ta", "te", "ml"})


class TranslationError(RuntimeError):
    pass


class TranslationService:
    def __init__(self, provider: TranslationProvider) -> None:
        self.provider = provider

    def detect_language(self, text: str) -> str:
        """Best-effort script detection; ASR language metadata remains authoritative."""
        counts = {
            "hi": len(re.findall(r"[\u0900-\u097f]", text)),
            "kn": len(re.findall(r"[\u0c80-\u0cff]", text)),
            "ta": len(re.findall(r"[\u0b80-\u0bff]", text)),
            "te": len(re.findall(r"[\u0c00-\u0c7f]", text)),
            "ml": len(re.findall(r"[\u0d00-\u0d7f]", text)),
        }
        language, count = max(counts.items(), key=lambda item: item[1])
        return language if count else "en"

    @staticmethod
    def _validate_language(language: str) -> str:
        normalized = language.strip().casefold()
        if normalized not in SUPPORTED_LANGUAGES:
            raise TranslationError(f"Unsupported language: {language}")
        return normalized

    async def translate_to_english(self, text: str, source_language: str) -> str:
        source = self._validate_language(source_language)
        if source == "en":
            return text
        return await self._translate(text, source, "en")

    async def translate_from_english(self, text: str, target_language: str) -> str:
        target = self._validate_language(target_language)
        if target == "en":
            return text
        return await self._translate(text, "en", target)

    async def _translate(self, text: str, source: str, target: str) -> str:
        if not text.strip():
            raise TranslationError("Cannot translate empty text")
        try:
            return await self.provider.translate_text(text, source, target)
        except Exception as exc:
            raise TranslationError(
                f"Translation from {source} to {target} failed"
            ) from exc


@lru_cache
def get_translation_service() -> TranslationService:
    return TranslationService(OllamaLocalAIProvider())
