"""Hybrid reference retrieval with Snowflake approval as the sole source of truth.

No cached embedding or LLM response can authorize a document. Candidate IDs,
department and APPROVED status are rechecked at every boundary. Semantic
similarity helps rank evidence, not grant permission or prove factual support.
"""
from __future__ import annotations

import asyncio
import logging
import math
import re
import unicodedata
from typing import Any, Mapping, Sequence

from starlette.concurrency import run_in_threadpool

from app.core.config import settings
from app.integrations.local_ai_provider import OllamaLocalAIProvider
from app.integrations.retrieval_providers import cosine_similarity
from app.repositories.reference_document_repository import ReferenceDocumentRepository

logger = logging.getLogger("workmate.reference_retrieval")

_STOPWORDS = frozenset({
    "a", "about", "all", "an", "and", "are", "can", "could", "do", "does",
    "for", "from", "how", "i", "in", "is", "it", "me", "my", "of", "on",
    "or", "our", "please", "should", "the", "this", "to", "us", "what",
    "when", "where", "which", "who", "why", "with", "would", "you", "your",
    "क्या", "कैसे", "कहां", "और", "यह", "उस", "है", "को", "से", "का", "की",
    "में", "पर", "मुझे", "हमें", "करें", "चाहिए",
})
# Small, curated equivalence sets are recall hints, never authorization rules.
# Avoid expanding antonyms or unverified operational actions.
_GROUPS = (
    ("carton", "cartons", "box", "boxes", "package", "packages", "parcel", "parcels", "पैकेज", "डिब्बा", "डिब्बे"),
    ("damage", "damaged", "broken", "defective", "क्षतिग्रस्त", "नुकसान", "टूटा"),
    ("seal", "seals", "सील"),
    ("quarantine", "isolate", "isolated", "segregate", "अलग", "क्वारंटीन"),
    ("shipment", "shipments", "consignment", "delivery", "शिपमेंट", "खेप"),
    ("receiving", "receive", "receipt", "received", "प्राप्त", "प्राप्ति"),
    ("inventory", "stock", "इन्वेंटरी", "भंडार"),
    ("barcode", "barcodes", "scan", "scanning", "बारकोड"),
    ("supervisor", "manager", "सुपरवाइजर", "पर्यवेक्षक"),
)
_CANONICAL = {word: group[0] for group in _GROUPS for word in group}


def tokens(text: str) -> tuple[str, ...]:
    """Unicode NFKC tokens retaining combining marks in Devanagari words."""
    normalized = unicodedata.normalize("NFKC", text or "").casefold()
    words = []
    buffer = []
    for char in normalized:
        if unicodedata.category(char)[:1] in {"L", "N", "M"}:
            buffer.append(char)
        elif buffer:
            words.append("".join(buffer))
            buffer = []
    if buffer:
        words.append("".join(buffer))
    return tuple(dict.fromkeys(
        word for word in words if len(word) >= 2 and word not in _STOPWORDS
    ))


def lexical_score(query: str, passage: str, title: str = "") -> float:
    """Whole-token coverage with modest title weighting; no substring shortcuts."""
    query_words = tokens(query)
    if not query_words:
        return 0.0
    body = {_CANONICAL.get(word, word) for word in tokens(passage)}
    titles = {_CANONICAL.get(word, word) for word in tokens(title)}
    coverage = sum(
        1.0 if _CANONICAL.get(term, term) in body
        else 0.45 if _CANONICAL.get(term, term) in titles
        else 0.0
        for term in query_words
    ) / len(query_words)
    return round(min(1.0, coverage), 4)


def script_affinity(question: str, evidence: str) -> float:
    """Prefer the user's script on ties; never block cross-language evidence."""
    def fraction(value: str) -> float:
        letters = [ch for ch in value if unicodedata.category(ch).startswith("L")]
        if not letters:
            return 0.0
        return sum("\\u0900" <= ch <= "\\u097f" for ch in letters) / len(letters)
    q, e = fraction(question), fraction(evidence)
    if 0.20 < q < 0.80:
        return 0.5  # Mixed-script questions should not be pinned to one script.
    return 1.0 if (q >= 0.5) == (e >= 0.5) else 0.0


def authorized(source: Mapping[str, Any], department_id: str) -> bool:
    return bool(
        source.get("department_id") == department_id
        and str(source.get("status", "")).upper() == "APPROVED"
        and source.get("document_id") and source.get("chunk_id")
        and source.get("document_title")
        and isinstance(source.get("excerpt"), str)
        and len(source["excerpt"].strip()) >= 15
    )


def rerank_lexical(query: str, sources: Sequence[Mapping[str, Any]], department_id: str,
                   limit: int = 10) -> list[dict[str, Any]]:
    """Deterministic fallback also used by the hermetic benchmark."""
    ranked: dict[str, dict[str, Any]] = {}
    for source in sources:
        if not authorized(source, department_id):
            continue
        value = dict(source)
        value["lexical_score"] = lexical_score(
            query, str(source["excerpt"]), str(source["document_title"])
        )
        value["semantic_score"] = None
        value["rank_score"] = round(
            0.92 * value["lexical_score"] + 0.08 * script_affinity(query, str(source["excerpt"])), 4
        )
        value["retrieval_method"] = "lexical"
        if value["lexical_score"] <= 0.0:
            continue
        key = str(value["chunk_id"])
        if key not in ranked or value["rank_score"] > ranked[key]["rank_score"]:
            ranked[key] = value
    return sorted(
        ranked.values(), key=lambda s: (-s["rank_score"], str(s["chunk_id"]))
    )[:limit]


class ReferenceRetrievalService:
    """Hybrid ranks only live-approved candidates; local AI failure is nonfatal."""

    provider = OllamaLocalAIProvider()

    @classmethod
    async def search(cls, query: str, department_id: str, *, limit: int = 10) -> list[dict[str, Any]]:
        if not query.strip() or not department_id.strip():
            return []
        limit = max(1, min(int(limit), 20))
        # Fetch the lexical shortlist and independent semantic pool from Snowflake,
        # never from a persistent vector cache that might contain archived text.
        lexical, pool = await asyncio.gather(
            run_in_threadpool(
                ReferenceDocumentRepository.search_approved,
                query, department_id, limit=40,
            ),
            run_in_threadpool(
                ReferenceDocumentRepository.list_approved_candidates,
                department_id, limit=settings.REFERENCE_POOL_LIMIT,
            ),
        )
        by_id: dict[str, dict[str, Any]] = {}
        for source in [*lexical, *pool]:
            if authorized(source, department_id):
                by_id[str(source["chunk_id"])] = dict(source)
        ranked = rerank_lexical(query, list(by_id.values()), department_id, limit=len(by_id) or 1)
        if not settings.REFERENCE_HYBRID_ENABLED or not settings.LOCAL_AI_ENABLED:
            return ranked[:limit]
        # Preserve strong lexical matches and a bounded sample of weaker/semantic
        # candidates; no unbounded 1M-token embedding request on each turn.
        selected = ranked[: settings.REFERENCE_EMBED_MAX_CANDIDATES // 2]
        selected_ids = {str(c["chunk_id"]) for c in selected}
        for source in sorted(by_id.values(), key=lambda row: str(row["chunk_id"])):
            if len(selected) >= settings.REFERENCE_EMBED_MAX_CANDIDATES:
                break
            if str(source["chunk_id"]) not in selected_ids:
                selected.append(source)
                selected_ids.add(str(source["chunk_id"]))
        if not selected:
            return []
        try:
            vectors = await asyncio.wait_for(
                cls.provider.embed(
                    [query[:300]] + [str(c["excerpt"])[:1000] for c in selected]
                ),
                timeout=settings.REFERENCE_SEMANTIC_TIMEOUT_SECONDS,
            )
            if len(vectors) != len(selected) + 1:
                raise ValueError("Embedding returned an incomplete batch")
            if not all(
                vector and all(math.isfinite(float(n)) for n in vector)
                for vector in vectors
            ):
                raise ValueError("Embedding contains nonfinite or empty vectors")
            query_vector = vectors[0]
            for row, vector in zip(selected, vectors[1:]):
                lexical_strength = lexical_score(
                    query, str(row["excerpt"]), str(row["document_title"])
                )
                semantic = max(0.0, cosine_similarity(query_vector, vector))
                row["lexical_score"] = lexical_strength
                row["semantic_score"] = round(semantic, 4)
                # Conservative semantic-only candidate: discovery/review rather
                # than a high-confidence quoted instruction.
                row["rank_score"] = round(
                    0.67 * lexical_strength + 0.28 * semantic
                    + 0.05 * script_affinity(query, str(row["excerpt"])), 4
                )
                row["retrieval_method"] = "hybrid"
            # Keep unembedded lexical candidates eligible, never hide reliable
            # exact keyword evidence merely because the pool cap was reached.
            remaining = [s for s in ranked if str(s["chunk_id"]) not in selected_ids]
            selected.extend(remaining)
            return sorted(
                (s for s in selected if authorized(s, department_id)),
                key=lambda s: (-s["rank_score"], str(s["chunk_id"])),
            )[:limit]
        except Exception as exc:
            logger.warning("Local reference embeddings unavailable (%s), using scoped lexical retrieval",
                           type(exc).__name__)
            return ranked[:limit]
