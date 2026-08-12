"""Provider-neutral AI gateway for local retrieval and generation."""

import logging
from typing import Any, Dict, List, Sequence

from app.core.config import settings
from app.integrations.ai_provider import GeneratedAnswer
from app.integrations.local_ai_provider import OllamaLocalAIProvider
from app.integrations.retrieval_providers import LocalSemanticIndex, SqlLexicalRetrievalProvider
from app.services.copilot_reasoning import CopilotReasoningService

logger = logging.getLogger("workmate.ai_gateway")


class ExtractiveGenerationProvider:
    """Safe deterministic response generated only from verified evidence."""

    async def generate(
        self, question: str, sources: Sequence[Dict[str, Any]]
    ) -> GeneratedAnswer:
        if not sources:
            return GeneratedAnswer(answer="", source_ids=[], provider="extractive")
        top = sources[0]
        source_id = str(top.get("chunk_id", ""))
        return GeneratedAnswer(
            answer=CopilotReasoningService.concise_extract(question, top),
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
        lowered = message.lower()
        if len(message.strip()) < 4:
            if history:
                return {"intent": "CONTEXTUAL_FOLLOW_UP", "needs_clarification": False}
            return {"intent": "AMBIGUOUS", "needs_clarification": True}
        if any(
            term in lowered
            for term in ("help", "what", "how", "sop", "step", "procedure", "process", "guide")
        ):
            return {"intent": "SOP_GUIDANCE", "needs_clarification": False}
        return {"intent": "GENERAL_QUERY", "needs_clarification": False}

    @classmethod
    async def plan_workflow_action(
        cls,
        message: str,
        history: List[Dict[str, Any]],
        workflow_context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Return a non-authoritative semantic plan for an ambiguous workflow move."""
        fallback = {
            "intent": "ask_guidance",
            "completion_scope": "none",
            "outcome_text": "",
            "needs_clarification": False,
            "confidence": 0.0,
            "authoritative": False,
        }
        if not settings.LOCAL_AI_ENABLED:
            return fallback
        try:
            return await cls.local_provider.plan_workflow_action(
                message, history, workflow_context
            )
        except Exception as exc:
            logger.warning(
                "Local workflow planning unavailable; preserving deterministic flow: %s",
                type(exc).__name__,
            )
            return fallback

    @classmethod
    async def classify_verified_instruction_followup(
        cls, message: str, verified_instruction: str
    ) -> Dict[str, Any]:
        """Classify how a follow-up relates to the last verified instruction."""
        fallback = {
            "relation": "unclear",
            "asks_next": False,
            "confidence": 0.0,
            "authoritative": False,
        }
        if not settings.LOCAL_AI_ENABLED:
            return fallback
        try:
            return await cls.local_provider.classify_verified_instruction_followup(
                message, verified_instruction
            )
        except Exception as exc:
            logger.warning(
                "Local verified-follow-up reasoning unavailable; using safe fallback: %s",
                type(exc).__name__,
            )
            return fallback

    @classmethod
    async def search(cls, query: str, department_id: str, limit: int = 5) -> List[Dict[str, Any]]:
        if not query.strip() or not department_id.strip():
            return []
        effective_limit = max(1, min(limit, settings.COPILOT_RETRIEVAL_LIMIT, 20))
        cached_fuzzy = cls.semantic_index.fuzzy_search_cached(
            query, department_id, effective_limit
        )
        if cached_fuzzy and float(cached_fuzzy[0].get("score", 0.0)) >= (
            settings.COPILOT_MIN_CONFIDENCE_THRESHOLD
        ):
            logger.info("Using strong cached typo-tolerant retrieval result")
            return cached_fuzzy
        lexical_results: List[Dict[str, Any]] = []
        try:
            lexical_results = await cls.sql_provider.search(
                query, department_id, effective_limit
            )
            if lexical_results and float(lexical_results[0].get("score", 0.0)) >= (
                settings.COPILOT_MIN_CONFIDENCE_THRESHOLD
            ):
                logger.info("Using strong scoped lexical retrieval result")
                return lexical_results
        except Exception as exc:
            logger.warning(
                "Scoped SQL retrieval unavailable; trying local semantic retrieval: %s",
                type(exc).__name__,
            )
        try:
            fuzzy_results = await cls.semantic_index.fuzzy_search(
                query, department_id, effective_limit
            )
            if fuzzy_results and float(fuzzy_results[0].get("score", 0.0)) >= (
                settings.COPILOT_MIN_CONFIDENCE_THRESHOLD
            ):
                logger.info("Using strong typo-tolerant retrieval result")
                return fuzzy_results
        except Exception as exc:
            logger.warning("Typo-tolerant retrieval unavailable: %s", type(exc).__name__)
        if settings.LOCAL_AI_ENABLED:
            try:
                results = await cls.semantic_index.search(query, department_id, effective_limit)
                if results:
                    return results
            except Exception as exc:
                logger.warning("Local semantic retrieval unavailable; using SQL fallback: %s", type(exc).__name__)
        return lexical_results

    @classmethod
    async def generate_response(cls, prompt_context: Dict[str, Any]) -> GeneratedAnswer:
        sources = prompt_context.get("retrieved_chunks", [])
        question = str(prompt_context.get("query", ""))
        agent_context = prompt_context.get("agent_context", {})
        if not sources:
            return GeneratedAnswer(answer="", source_ids=[], provider="none")
        if settings.LOCAL_AI_ENABLED:
            try:
                return await cls.local_provider.generate_grounded(
                    question, sources, agent_context
                )
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
    async def get_workflow_state_source(
        cls,
        department_id: str,
        workflow_version_id: str,
        state_id: str,
    ) -> Dict[str, Any] | None:
        return await cls.semantic_index.get_workflow_state_source(
            department_id, workflow_version_id, state_id
        )

    @classmethod
    async def health(cls) -> Dict[str, Any]:
        return await cls.local_provider.health()
