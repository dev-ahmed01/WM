"""Provider-neutral contracts for WorkMate's self-hosted AI runtime."""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Protocol, Sequence


@dataclass(frozen=True)
class GeneratedAnswer:
    """Structured answer whose source IDs must map to retrieved evidence."""

    answer: str
    source_ids: List[str] = field(default_factory=list)
    provider: str = "unknown"


class LocalAIProvider(Protocol):
    async def health(self) -> Dict[str, Any]: ...
    async def embed(self, texts: Sequence[str]) -> List[List[float]]: ...
    async def generate_grounded(
        self,
        question: str,
        sources: Sequence[Dict[str, Any]],
        context: Dict[str, Any] | None = None,
    ) -> GeneratedAnswer: ...
    async def extract_answer(
        self, question: str, sources: Sequence[Dict[str, Any]]
    ) -> GeneratedAnswer: ...
    async def summarize(self, sources: Sequence[Dict[str, Any]]) -> GeneratedAnswer: ...
    async def classify_suggestion(self, text: str, labels: Sequence[str]) -> Dict[str, Any]: ...


class RetrievalProvider(Protocol):
    async def search(
        self, query: str, department_id: str, limit: int
    ) -> List[Dict[str, Any]]: ...


class GenerationProvider(Protocol):
    async def generate(
        self, question: str, sources: Sequence[Dict[str, Any]]
    ) -> GeneratedAnswer: ...


class TranslationProvider(Protocol):
    async def translate_text(
        self, text: str, source_language: str, target_language: str
    ) -> str: ...
