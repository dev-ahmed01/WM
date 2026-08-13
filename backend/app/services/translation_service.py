"""Provider-neutral English/Hindi translation for the Copilot voice pipeline."""

import re
from difflib import SequenceMatcher
from functools import lru_cache

from app.integrations.ai_provider import TranslationProvider
from app.integrations.hindi_translation_provider import CTranslate2HindiProvider

SUPPORTED_LANGUAGES = frozenset({"en", "hi"})
_HINDI_OPERATIONAL_WORDS = (
    "मुझे",
    "सामान",
    "प्राप्त",
    "करने",
    "प्रक्रिया",
    "बता",
    "बताइए",
)


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
        normalized = self.normalize_operational_transcript(text, source)
        return await self._translate(normalized, source, "en")

    @staticmethod
    def normalize_operational_transcript(text: str, language: str) -> str:
        """Repair near-word ASR errors without guessing an operational action."""
        if language != "hi":
            return text

        def replace(match: re.Match[str]) -> str:
            word = match.group(0)
            # In WorkMate's warehouse domain, this noun means physical goods;
            # M2M100 otherwise commonly translates it as financial wealth.
            if word == "माल":
                return "सामान"
            candidate = max(
                _HINDI_OPERATIONAL_WORDS,
                key=lambda known: SequenceMatcher(None, word, known).ratio(),
            )
            similarity = SequenceMatcher(None, word, candidate).ratio()
            same_sound_start = word[0] == candidate[0] or {word[0], candidate[0]} == {"ब", "व"}
            if same_sound_start and abs(len(word) - len(candidate)) <= 2 and similarity >= 0.65:
                return candidate
            return word

        normalized = re.sub(r"[\u0900-\u097f]+", replace, text)
        return re.sub(r"\bबता\s+हीए\b", "बताइए", normalized)

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
