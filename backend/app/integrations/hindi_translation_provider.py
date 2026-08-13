"""Compact English/Hindi translation on the existing CTranslate2 runtime."""

import logging
from pathlib import Path
from threading import Lock
from typing import Any

from starlette.concurrency import run_in_threadpool

from app.core.config import settings

logger = logging.getLogger("workmate.voice.translation")


class CTranslate2HindiProvider:
    """Use one quantized M2M100 model for both English/Hindi directions."""

    def __init__(self) -> None:
        self._translator: Any = None
        self._tokenizer: Any = None
        self._load_lock = Lock()
        self._inference_lock = Lock()

    def _load(self) -> tuple[Any, Any]:
        if self._translator is not None and self._tokenizer is not None:
            return self._translator, self._tokenizer
        with self._load_lock:
            if self._translator is not None and self._tokenizer is not None:
                return self._translator, self._tokenizer
            model_dir = Path(settings.HINDI_TRANSLATION_MODEL_DIR)
            if not model_dir.is_dir():
                raise RuntimeError(f"Hindi translation model is missing: {model_dir}")

            import ctranslate2
            import sentencepiece as spm

            logger.info("Loading quantized M2M100 English/Hindi translator")
            self._translator = ctranslate2.Translator(
                str(model_dir),
                device="cpu",
                compute_type="int8",
                inter_threads=1,
                intra_threads=settings.HINDI_TRANSLATION_CPU_THREADS,
            )
            self._tokenizer = spm.SentencePieceProcessor(
                model_file=str(model_dir / "sentencepiece.bpe.model")
            )
            return self._translator, self._tokenizer

    def _translate_sync(self, text: str, source: str, target: str) -> str:
        if {source, target} != {"en", "hi"}:
            raise ValueError(f"Unsupported translation direction: {source}->{target}")
        with self._inference_lock:
            translator, tokenizer = self._load()
            source_tokens = [
                f"__{source}__",
                *tokenizer.encode(text, out_type=str),
                "</s>",
            ]
            target_prefix = [f"__{target}__"]
            result = translator.translate_batch(
                [source_tokens],
                target_prefix=[target_prefix],
                beam_size=settings.HINDI_TRANSLATION_BEAM_SIZE,
                max_decoding_length=512,
                repetition_penalty=1.05,
            )[0]
            target_tokens = [
                token
                for token in result.hypotheses[0][1:]
                if token not in {"</s>", "<pad>"} and not token.startswith("__")
            ]
            translation = tokenizer.decode(target_tokens).strip()
        if not translation:
            raise RuntimeError("Hindi translator returned empty text")
        return translation

    async def translate_text(
        self, text: str, source_language: str, target_language: str
    ) -> str:
        return await run_in_threadpool(
            self._translate_sync, text, source_language, target_language
        )

    async def warm(self) -> None:
        """Load the quantized translator before the first voice request."""
        await run_in_threadpool(self._load)
