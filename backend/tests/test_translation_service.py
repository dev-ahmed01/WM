"""Multilingual translation service tests."""

from unittest.mock import AsyncMock

import pytest

from app.services.translation_service import TranslationError, TranslationService


def test_detect_language_supports_indic_scripts():
    service = TranslationService(AsyncMock())
    assert service.detect_language("मुझे सहायता चाहिए") == "hi"
    assert service.detect_language("ನನಗೆ ಸಹಾಯ ಬೇಕು") == "kn"
    assert service.detect_language("எனக்கு உதவி வேண்டும்") == "ta"
    assert service.detect_language("నాకు సహాయం కావాలి") == "te"
    assert service.detect_language("എനിക്ക് സഹായം വേണം") == "ml"
    assert service.detect_language("I need help") == "en"


@pytest.mark.asyncio
async def test_english_translation_is_a_noop():
    provider = AsyncMock()
    service = TranslationService(provider)
    assert await service.translate_to_english("check the seal", "en") == "check the seal"
    assert await service.translate_from_english("check the seal", "en") == "check the seal"
    provider.translate_text.assert_not_awaited()


@pytest.mark.asyncio
async def test_translation_uses_provider_in_both_directions():
    provider = AsyncMock()
    provider.translate_text.side_effect = ["inspect damage", "क्षति की जाँच करें"]
    service = TranslationService(provider)

    assert await service.translate_to_english("क्षति देखें", "hi") == "inspect damage"
    assert await service.translate_from_english("inspect damage", "hi") == "क्षति की जाँच करें"
    assert provider.translate_text.await_args_list[0].args == ("क्षति देखें", "hi", "en")
    assert provider.translate_text.await_args_list[1].args == ("inspect damage", "en", "hi")


@pytest.mark.asyncio
async def test_unsupported_translation_language_is_rejected():
    with pytest.raises(TranslationError, match="Unsupported language"):
        await TranslationService(AsyncMock()).translate_to_english("bonjour", "fr")
