"""Provider-neutral AI gateway for local retrieval and generation."""

import logging
from typing import Any, Dict, List, Sequence

from app.core.config import settings
from app.integrations.ai_provider import GeneratedAnswer
from app.integrations.local_ai_provider import OllamaLocalAIProvider
from app.integrations.retrieval_providers import LocalSemanticIndex, SqlLexicalRetrievalProvider

logger = logging.getLogger("workmate.ai_gateway")


class ExtractiveGenerationProvider:
    """Safe deterministic response generated only from verified evidence."""

    async def generate(
        self, question: str, sources: Sequence[Dict[str, Any]]
    ) -> GeneratedAnswer:
        del question
        if not sources:
            return GeneratedAnswer(answer="", source_ids=[], provider="extractive")
        top = sources[0]
        source_id = str(top.get("chunk_id", ""))
        return GeneratedAnswer(
            answer=(
                f"According to '{top.get('document_title', 'the retrieved SOP')}' "
                f"(v{top.get('version_number', 'unknown')}), "
                f"{str(top.get('content', '')).strip()}"
            ),
            source_ids=[source_id] if source_id else [],
            provider="extractive",
        )


class AIGateway:
    """Coordinates local AI and deterministic fallbacks without external providers."""

    local_provider = OllamaLocalAIProvider()
    semantic_index = LocalSemanticIndex(local_provider)
    sql_provider = SqlLexicalRetrievalProvider()
    extractive_provider = ExtractiveGenerationProvider()

    @staticmethod
    async def detect_intent(message: str, history: List[Dict[str, Any]]) -> Dict[str, Any]:
        del history
        lowered = message.lower()
        if len(message.strip()) < 4:
            return {"intent": "AMBIGUOUS", "needs_clarification": True}
        if any(term in lowered for term in ("help", "what", "how", "sop")):
            return {"intent": "SOP_GUIDANCE", "needs_clarification": False}
        return {"intent": "GENERAL_QUERY", "needs_clarification": False}

    @classmethod
    async def search(cls, query: str, department_id: str, limit: int = 5) -> List[Dict[str, Any]]:
        if not query.strip() or not department_id.strip():
            return []
        effective_limit = max(1, min(limit, settings.COPILOT_RETRIEVAL_LIMIT, 20))
        if settings.LOCAL_AI_ENABLED:
            try:
                results = await cls.semantic_index.search(query, department_id, effective_limit)
                if results:
                    return results
            except Exception as exc:
                logger.warning("Local semantic retrieval unavailable; using SQL fallback: %s", type(exc).__name__)
        return await cls.sql_provider.search(query, department_id, effective_limit)

    @classmethod
    async def generate_response(cls, prompt_context: Dict[str, Any]) -> GeneratedAnswer:
        sources = prompt_context.get("retrieved_chunks", [])
        question = str(prompt_context.get("query", ""))
        if not sources:
            return GeneratedAnswer(answer="", source_ids=[], provider="none")
        if settings.LOCAL_AI_ENABLED:
            try:
                return await cls.local_provider.generate_grounded(question, sources)
            except Exception as exc:
                logger.warning("Local generation unavailable; using extractive fallback: %s", type(exc).__name__)
        return await cls.extractive_provider.generate(question, sources)

    @classmethod
    def invalidate_department(cls, department_id: str) -> None:
        cls.semantic_index.invalidate_department(department_id)

    @classmethod
    def invalidate_all(cls) -> None:
        cls.semantic_index.clear()

    @classmethod
    async def health(cls) -> Dict[str, Any]:
        return await cls.local_provider.health()
