"""Mandatory grounding, RBAC, citation, confidence, and fallback gate."""

import logging
import re
from typing import Any, Dict, List, Sequence, Tuple

from app.core.config import settings
from app.integrations.ai_provider import GeneratedAnswer
from app.models.copilot import Citation, ValidatedResponse

validation_logger = logging.getLogger("copilot_services")

CANONICAL_FALLBACK = (
    "I could not find verified organizational guidance for this request. "
    "Please contact your supervisor or administrator. The closest related documentation is provided below."
)

_STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "has", "in", "is",
    "it", "of", "on", "or", "that", "the", "this", "to", "was", "were", "with", "your",
}
_REQUIRED_METADATA = (
    "chunk_id",
    "document_id",
    "document_title",
    "version_number",
    "step_number",
    "content",
    "department_id",
    "status",
    "score",
)


class ResponseValidationService:
    """Reject unsupported model output and never fabricate citation metadata."""

    @staticmethod
    def _tokens(text: str) -> set[str]:
        return {
            token
            for token in re.findall(r"[a-z0-9][a-z0-9_-]{1,}", text.lower())
            if token not in _STOP_WORDS
        }

    @staticmethod
    def _has_complete_metadata(chunk: Dict[str, Any]) -> bool:
        if any(chunk.get(field) is None or chunk.get(field) == "" for field in _REQUIRED_METADATA):
            return False
        try:
            score = float(chunk["score"])
            int(chunk["version_number"])
        except (TypeError, ValueError):
            return False
        return 0.0 <= score <= 1.0

    @staticmethod
    def check_permissions(user_department_id: str, chunks: Sequence[Dict[str, Any]]) -> bool:
        """Every candidate must already match the authenticated department."""
        return bool(chunks) and all(
            chunk.get("department_id") == user_department_id for chunk in chunks
        )

    @classmethod
    def _source_map(
        cls, chunks: Sequence[Dict[str, Any]], user_department_id: str
    ) -> Dict[str, Dict[str, Any]]:
        allowed_statuses = {
            value.strip().lower()
            for value in settings.COPILOT_ALLOWED_KNOWLEDGE_STATUSES.split(",")
            if value.strip()
        } or {"published"}
        result: Dict[str, Dict[str, Any]] = {}
        for chunk in chunks:
            if not cls._has_complete_metadata(chunk):
                continue
            if chunk.get("department_id") != user_department_id:
                continue
            if str(chunk.get("status", "")).lower() not in allowed_statuses:
                continue
            result[str(chunk["chunk_id"])] = chunk
        return result

    @classmethod
    def has_relevant_evidence(
        cls,
        chunks: Sequence[Dict[str, Any]],
        user_department_id: str,
        min_confidence_threshold: float | None = None,
    ) -> bool:
        """Return whether authorized evidence is strong enough to answer or start a workflow."""
        threshold = (
            settings.COPILOT_MIN_CONFIDENCE_THRESHOLD
            if min_confidence_threshold is None
            else min_confidence_threshold
        )
        source_map = cls._source_map(chunks, user_department_id)
        return bool(source_map) and max(
            float(chunk["score"]) for chunk in source_map.values()
        ) >= threshold

    @classmethod
    def verify_grounding(
        cls, generated: GeneratedAnswer, cited_chunks: Sequence[Dict[str, Any]]
    ) -> Tuple[bool, float]:
        """Require real source IDs and material lexical support for generated claims."""
        if not generated.answer.strip() or not generated.source_ids or not cited_chunks:
            return False, 0.0
        evidence_tokens = set().union(
            *(cls._tokens(str(chunk["content"])) for chunk in cited_chunks)
        )
        answer_tokens = cls._tokens(generated.answer)
        if not answer_tokens or not evidence_tokens:
            return False, 0.0
        overlap = answer_tokens & evidence_tokens
        required_overlap = min(2, len(answer_tokens))
        if len(overlap) < required_overlap:
            return False, 0.0
        support_ratio = len(overlap) / len(answer_tokens)
        return support_ratio >= 0.15, min(support_ratio, 1.0)

    @staticmethod
    def generate_citations(chunks: Sequence[Dict[str, Any]]) -> List[Citation]:
        """Build citations only from complete, verified Snowflake metadata."""
        return [
            Citation(
                document_id=str(chunk["document_id"]),
                document_title=str(chunk["document_title"]),
                version_number=int(chunk["version_number"]),
                step_number=chunk["step_number"],
                chunk_id=str(chunk["chunk_id"]),
                excerpt=str(chunk["content"])[:300],
            )
            for chunk in chunks
        ]

    @staticmethod
    def estimate_confidence(
        cited_chunks: Sequence[Dict[str, Any]], support_ratio: float
    ) -> float:
        """Combine measured retrieval strength and measured textual support."""
        if not cited_chunks or support_ratio <= 0.0:
            return 0.0
        retrieval_strength = min(float(chunk["score"]) for chunk in cited_chunks)
        return round(retrieval_strength * (0.6 + 0.4 * support_ratio), 2)

    @classmethod
    def _canonical(cls) -> Tuple[ValidatedResponse, bool]:
        return (
            ValidatedResponse(
                answer=CANONICAL_FALLBACK,
                citations=[],
                confidence_score=0.0,
                is_grounded=False,
                requires_escalation=True,
            ),
            True,
        )

    @classmethod
    def _extractive_review_fallback(
        cls, source_map: Dict[str, Dict[str, Any]]
    ) -> Tuple[ValidatedResponse, bool]:
        if not source_map:
            return cls._canonical()
        top = max(source_map.values(), key=lambda chunk: float(chunk["score"]))
        answer = (
            f"Verified extract from '{top['document_title']}' (v{top['version_number']}, "
            f"step {top['step_number']}): {str(top['content']).strip()}"
        )
        return (
            ValidatedResponse(
                answer=answer,
                citations=cls.generate_citations([top]),
                confidence_score=round(float(top["score"]), 2),
                is_grounded=True,
                requires_escalation=True,
            ),
            True,
        )

    @classmethod
    def validate_response(
        cls,
        raw_response: GeneratedAnswer,
        retrieved_chunks: List[Dict[str, Any]],
        user_role: str,
        user_department_id: str,
        min_confidence_threshold: float | None = None,
    ) -> Tuple[ValidatedResponse, bool]:
        """Validate structured source IDs, evidence support, metadata, and RBAC."""
        del user_role  # Roles never bypass department isolation.
        threshold = (
            settings.COPILOT_MIN_CONFIDENCE_THRESHOLD
            if min_confidence_threshold is None
            else min_confidence_threshold
        )
        validation_logger.info("Executing response validation gate")
        if not retrieved_chunks or not cls.check_permissions(user_department_id, retrieved_chunks):
            return cls._canonical()

        source_map = cls._source_map(retrieved_chunks, user_department_id)
        if not source_map:
            return cls._canonical()
        if max(float(chunk["score"]) for chunk in source_map.values()) < threshold:
            validation_logger.warning("Retrieved evidence failed relevance threshold")
            return cls._canonical()

        source_ids = list(dict.fromkeys(raw_response.source_ids))
        if not source_ids or any(source_id not in source_map for source_id in source_ids):
            validation_logger.warning("Generated answer cited missing or unauthorized source IDs")
            return cls._extractive_review_fallback(source_map)

        cited_chunks = [source_map[source_id] for source_id in source_ids]
        grounded, support_ratio = cls.verify_grounding(raw_response, cited_chunks)
        confidence = cls.estimate_confidence(cited_chunks, support_ratio)
        if not grounded or confidence < threshold:
            validation_logger.warning("Generated answer failed grounding or confidence threshold")
            return cls._extractive_review_fallback(source_map)

        validated = ValidatedResponse(
            answer=raw_response.answer.strip(),
            citations=cls.generate_citations(cited_chunks),
            confidence_score=confidence,
            is_grounded=True,
            requires_escalation=False,
        )
        return validated, False
