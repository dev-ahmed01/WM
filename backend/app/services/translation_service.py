"""Provider-neutral English/Hindi translation for the Copilot voice pipeline."""

import re
from functools import lru_cache

from app.integrations.ai_provider import TranslationProvider
from app.integrations.hindi_translation_provider import CTranslate2HindiProvider

SUPPORTED_LANGUAGES = frozenset({"en", "hi"})


class TranslationError(RuntimeError):
    pass


class TranslationService:
    def __init__(self, provider: TranslationProvider) -> None:
        self.provider = provider

    def detect_language(self, text: str) -> str:
        """Best-effort script detection; ASR language metadata remains authoritative."""
        counts = {"hi": len(re.findall(r"[\u0900-\u097f]", text))}
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

    async def warm(self) -> None:
        warm = getattr(self.provider, "warm", None)
        if warm is not None:
            await warm()


@lru_cache
def get_translation_service() -> TranslationService:
    return TranslationService(CTranslate2HindiProvider())
