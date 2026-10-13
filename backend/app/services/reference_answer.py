"""Evidence-first reference answering without executable workflow authority.

Approved reference chunks are *not* instructions for the state machine. This
service returns only verbatim source language, never invented procedures, and
requires complete provenance from PostgreSQL department and approval checks.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any, Mapping, Sequence


from app.models.copilot import Citation, ValidatedResponse
from app.services.validation import CANONICAL_FALLBACK
from app.services.reference_retrieval import ReferenceRetrievalService, lexical_score, tokens, script_affinity
from app.repositories.reference_document_repository import ReferenceDocumentRepository
from starlette.concurrency import run_in_threadpool

# These are conversational fillers, not evidence-bearing terms.
_STOPWORDS = frozenset({
    "a", "an", "about", "and", "are", "can", "could", "do", "does", "for",
    "from", "how", "i", "if", "in", "is", "it", "me", "my", "of", "on",
    "or", "our", "please", "say", "should", "the", "this", "to", "us",
    "what", "when", "where", "which", "who", "why", "with", "would",
    "you", "your", "मुझे", "क्या", "कैसे", "है", "और", "में", "की", "का",
    "लिए", "अगर", "तो", "पर", "हम", "हमें",
})


def _terms(text: str) -> tuple[str, ...]:
    # Shared tokenization retains Hindi combining marks for both retrieval
    # ranking and the final evidence support threshold.
    return tokens(text)


@dataclass(frozen=True)
class _Passage:
    source: Mapping[str, Any]
    quote: str
    quote_offset: int
    relevance: float


class ReferenceAnswerService:
    """Deterministic source selection, with a mandatory exact-span validation gate."""

    @staticmethod
    def _candidate_passages(query: str, sources: Sequence[Mapping[str, Any]], department_id: str) -> list[_Passage]:
        terms = _terms(query)
        if not terms:
            return []
        candidates: list[_Passage] = []
        for source in sources:
            # Repository SQL does this too, but never trust a cache/test double.
            if (source.get("department_id") != department_id
                    or str(source.get("status", "")).upper() != "APPROVED"
                    or not source.get("document_id") or not source.get("chunk_id")
                    or not source.get("document_title")):
                continue
            content = source.get("excerpt")
            if not isinstance(content, str) or len(content.strip()) < 15:
                continue
            # A bounded excerpt may contain overlapping sentences. Select the
            # strongest *literal* phrase; don't synthesize an operational step.
            spans = [part.strip() for part in re.split(r"(?<=[.!?।])\s+|\n+", content) if part.strip()]
            if not spans:
                spans = [content]
            for passage in spans:
                if len(passage) < 15:
                    continue
                passage_terms = set(_terms(passage))
                exact = sum(1 for word in terms if word in passage_terms)
                fuzzy = sum(
                    1 for word in terms
                    if word not in passage_terms and any(
                        len(word) >= 4 and len(candidate) >= 4
                        and word[0] == candidate[0]
                        and SequenceMatcher(None, word, candidate).ratio() >= 0.87
                        for candidate in passage_terms
                    )
                )
                overlap = (exact + 0.35 * fuzzy) / len(terms)
                # Curated warehouse synonyms can bridge 'broken box' and
                # 'damaged carton', but never rely on embeddings alone as proof.
                normalized_coverage = lexical_score(query, passage)
                if (exact < 1 and normalized_coverage < 0.60) or max(overlap, normalized_coverage) < 0.40:
                    continue
                passage_start = content.find(passage)
                if passage_start < 0:
                    continue
                # Coverage is an actual observed proportion, not a model guess.
                relevance = round(min(1.0, max(overlap, normalized_coverage)), 3)
                candidates.append(_Passage(source, passage, passage_start, relevance))
        candidates.sort(key=lambda p: (-p.relevance, -script_affinity(query, p.quote), len(p.quote), str(p.source["chunk_id"])))
        return candidates

    @classmethod
    def validate_reference_answer(
        cls, query: str, sources: Sequence[Mapping[str, Any]], department_id: str,
    ) -> ValidatedResponse:
        """Fail closed unless every emitted citation resolves to a verbatim approved span."""
        candidate = next(iter(cls._candidate_passages(query, sources, department_id)), None)
        if candidate is None or candidate.relevance < 0.60:
            return ValidatedResponse(
                answer=CANONICAL_FALLBACK, citations=[], confidence_score=0.0,
                is_grounded=False, requires_escalation=True,
            )
        source = candidate.source
        text = str(source["excerpt"])
        quote = candidate.quote[:420].rstrip()
        if quote not in text:
            # Never return non-verbatim content based on a candidate's score.
            return ValidatedResponse(
                answer=CANONICAL_FALLBACK, citations=[], confidence_score=0.0,
                is_grounded=False, requires_escalation=True,
            )
        try:
            absolute_start = int(source["start_offset"]) + candidate.quote_offset
            original_end = int(source["end_offset"])
            chunk_index = int(source["chunk_index"])
        except (KeyError, ValueError, TypeError):
            return ValidatedResponse(
                answer=CANONICAL_FALLBACK, citations=[], confidence_score=0.0,
                is_grounded=False, requires_escalation=True,
            )
        if absolute_start < 0 or absolute_start + len(quote) > original_end or chunk_index < 0:
            return ValidatedResponse(
                answer=CANONICAL_FALLBACK, citations=[], confidence_score=0.0,
                is_grounded=False, requires_escalation=True,
            )
        citation = Citation(
            document_id=str(source["document_id"]),
            document_title=str(source["document_title"]),
            version_number=None, step_number=None,
            chunk_id=str(source["chunk_id"]),
            excerpt=quote,
            source_type="reference",
            section_anchor=f"excerpt {chunk_index + 1}, chars {absolute_start}–{absolute_start + len(quote)}",
        )
        return ValidatedResponse(
            answer=f"From an approved reference document:\n\n“{quote}”\n\nThis is reference information, not a recorded workflow step.",
            citations=[citation],
            confidence_score=candidate.relevance,
            is_grounded=True,
            requires_escalation=False,
        )

    @classmethod
    async def answer(cls, query: str, department_id: str) -> ValidatedResponse:
        # Database code is synchronous: keep ASGI event loop responsive.
        results = await ReferenceRetrievalService.search(query, department_id, limit=20)
        evaluated = cls.validate_reference_answer(query, results, department_id)
        # A reference can be archived after ranking but before answer emission.
        # Recheck the authoritative PostgreSQL approval state before returning
        # even an exact quoted passage. No caching of reviewer decisions.
        for citation in evaluated.citations:
            current = await run_in_threadpool(
                ReferenceDocumentRepository.get_document,
                citation.document_id, department_id,
            )
            if not current or current.get("status") != "APPROVED":
                return ValidatedResponse(
                    answer=CANONICAL_FALLBACK, citations=[], confidence_score=0.0,
                    is_grounded=False, requires_escalation=True,
                )
        return evaluated
