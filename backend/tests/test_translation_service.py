"""English/Hindi translation service tests."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services.translation_service import TranslationError, TranslationService
from app.integrations.hindi_translation_provider import CTranslate2HindiProvider


def test_detect_language_supports_indic_scripts():
    service = TranslationService(AsyncMock())
    assert service.detect_language("मुझे सहायता चाहिए") == "hi"
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


@pytest.mark.asyncio
@pytest.mark.parametrize("language", ["kn", "ta", "te", "ml"])
async def test_removed_regional_languages_are_rejected(language):
    with pytest.raises(TranslationError, match="Unsupported language"):
        await TranslationService(AsyncMock()).translate_to_english("test", language)


def test_compact_provider_uses_m2m_language_tokens_without_transformers():
    class FakeTokenizer:
        def encode(self, text, out_type):
            assert text == "क्षतिग्रस्त पैकेज"
            assert out_type is str
            return ["▁source"]

        def decode(self, tokens):
            assert tokens == ["▁damaged", "▁package"]
            return "damaged package"

    class FakeTranslator:
        def translate_batch(self, batch, **kwargs):
            assert batch == [["__hi__", "▁source", "</s>"]]
            assert kwargs["target_prefix"] == [["__en__"]]
            return [
                SimpleNamespace(
                    hypotheses=[["__en__", "▁damaged", "▁package", "</s>"]]
                )
            ]

    provider = CTranslate2HindiProvider()
    provider._tokenizer = FakeTokenizer()
    provider._translator = FakeTranslator()

    assert provider._translate_sync("क्षतिग्रस्त पैकेज", "hi", "en") == "damaged package"
