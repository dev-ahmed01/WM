"""Provider-neutral retrieval with a disposable local semantic index."""

import asyncio
from difflib import SequenceMatcher
import logging
import math
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Sequence, Tuple

from app.core.config import settings
from app.core.database import get_snowflake_connection
from app.exceptions import WorkMateException
from app.integrations.ai_provider import LocalAIProvider

logger = logging.getLogger("workmate.retrieval")

_STOP_WORDS = {
    "a", "an", "and", "are", "do", "for", "how", "i", "if", "in", "is", "it",
    "give", "me", "of", "on", "please", "show", "step", "steps", "should", "the",
    "its", "to", "what", "when", "where", "with", "you",
}


def allowed_statuses() -> Tuple[str, ...]:
    statuses = tuple(
        value.strip().lower()
        for value in settings.COPILOT_ALLOWED_KNOWLEDGE_STATUSES.split(",")
        if value.strip()
    )
    return statuses or ("published",)


def _is_stop_word(term: str) -> bool:
    if term in _STOP_WORDS:
        return True
    if len(term) < 3:
        return False
    return any(
        abs(len(term) - len(stop_word)) <= 1
        and term[0] == stop_word[0]
        and SequenceMatcher(None, term, stop_word).ratio() >= 0.82
        for stop_word in _STOP_WORDS
    )


def search_terms(query: str) -> List[str]:
    terms = re.findall(r"[a-z0-9][a-z0-9_-]{1,}", (query or "").lower())
    result: List[str] = []
    for term in terms:
        if not _is_stop_word(term) and term not in result:
            result.append(term)
    return result[:8]


def fuzzy_relevance_score(query: str, candidate_content: str) -> float:
    """Score typo-tolerant token overlap without changing or generating SOP text."""
    query_tokens = search_terms(query)
    if not query_tokens:
        return 0.0
    candidate_tokens = set(
        re.findall(r"[a-z0-9][a-z0-9_-]{1,}", (candidate_content or "").lower())
    )
    qualities: List[float] = []
    for query_token in query_tokens:
        if query_token in candidate_tokens:
            qualities.append(1.0)
            continue
        if len(query_token) < 4:
            continue
        threshold = 0.72 if len(query_token) >= 6 else 0.74
        best = max(
            (
                SequenceMatcher(None, query_token, candidate_token).ratio()
                for candidate_token in candidate_tokens
                if candidate_token
                and candidate_token[0] == query_token[0]
                and abs(len(candidate_token) - len(query_token)) <= 2
            ),
            default=0.0,
        )
        if best >= threshold:
            qualities.append(best)
    # Requiring up to four independently matching terms prevents a single
    # incidental fuzzy match from crossing the response safety threshold.
    denominator = min(len(query_tokens), 4)
    return round(min(1.0, sum(sorted(qualities, reverse=True)[:4]) / denominator), 6)


def cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    """Compute similarity independently of the configured embedding provider."""
    if not left or len(left) != len(right):
        return 0.0
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    return sum(a * b for a, b in zip(left, right)) / (left_norm * right_norm)


class CandidateRepository:
    """Reads authorized candidates from Snowflake; it performs no AI work."""

    @staticmethod
    def load_page(
        department_id: str,
        statuses: Sequence[str],
        page_size: int,
        offset: int,
    ) -> List[Dict[str, Any]]:
        placeholders = ", ".join(["%s"] * len(statuses))
        sql = f"""
            SELECT sm.id AS chunk_id,
                   w.id AS document_id,
                   w.title AS document_title,
                   wv.id AS workflow_version_id,
                   wv.version_number,
                   s.id AS state_id,
                   s.ordinal_index AS step_number,
                   s.title AS step_title,
                   sm.search_content AS content,
                   sm.department_id,
                   LOWER(wv.status) AS status
            FROM WORKMATE_AI.KNOWLEDGE_STUDIO.workflow_search_metadata sm
            JOIN WORKMATE_AI.KNOWLEDGE_STUDIO.workflow_versions wv
              ON sm.workflow_version_id = wv.id
            JOIN WORKMATE_AI.KNOWLEDGE_STUDIO.workflows w
              ON wv.workflow_id = w.id
            JOIN WORKMATE_AI.KNOWLEDGE_STUDIO.workflow_states s
              ON sm.state_id = s.id
            WHERE LOWER(wv.status) IN ({placeholders})
              AND LOWER(sm.status) = 'published'
              AND sm.department_id = %s
              AND w.department_id = %s
              AND wv.version_number = (
                  SELECT MAX(candidate_version.version_number)
                  FROM WORKMATE_AI.KNOWLEDGE_STUDIO.workflow_versions candidate_version
                  WHERE candidate_version.workflow_id = wv.workflow_id
                    AND LOWER(candidate_version.status) IN ({placeholders})
              )
            ORDER BY sm.id
            LIMIT %s OFFSET %s
        """
        params: List[Any] = [
            *statuses,
            department_id,
            department_id,
            *statuses,
            page_size,
            offset,
        ]
        with get_snowflake_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(sql, params)
                rows = cursor.fetchall()
                columns = [column[0].lower() for column in cursor.description]
                return [dict(zip(columns, row)) for row in rows]


@dataclass
class SemanticIndexEntry:
    candidates: List[Dict[str, Any]]
    embeddings: List[List[float]]


class LocalSemanticIndex:
    """Bounded in-memory index that is fully rebuildable from Snowflake."""

    def __init__(self, provider: LocalAIProvider):
        self.provider = provider
        self._entries: Dict[Tuple[str, Tuple[str, ...], str], SemanticIndexEntry] = {}
        self._candidate_entries: Dict[
            Tuple[str, Tuple[str, ...], str], List[Dict[str, Any]]
        ] = {}
        self._locks: Dict[Tuple[str, Tuple[str, ...], str], asyncio.Lock] = {}

    def _key(self, department_id: str) -> Tuple[str, Tuple[str, ...], str]:
        return department_id, allowed_statuses(), settings.LOCAL_EMBEDDING_MODEL

    def invalidate_department(self, department_id: str) -> None:
        for key in [key for key in self._entries if key[0] == department_id]:
            self._entries.pop(key, None)
        for key in [key for key in self._candidate_entries if key[0] == department_id]:
            self._candidate_entries.pop(key, None)

    def clear(self) -> None:
        self._entries.clear()
        self._candidate_entries.clear()

    async def get_candidates(self, department_id: str) -> List[Dict[str, Any]]:
        key = self._key(department_id)
        cached = self._candidate_entries.get(key)
        if cached is not None:
            return cached
        lock = self._locks.setdefault(key, asyncio.Lock())
        async with lock:
            cached = self._candidate_entries.get(key)
            if cached is not None:
                return cached
            statuses = key[1]
            page_size = max(1, settings.LOCAL_AI_CANDIDATE_LIMIT)
            max_candidates = max(page_size, settings.LOCAL_AI_INDEX_MAX_CANDIDATES)
            candidates: List[Dict[str, Any]] = []
            offset = 0
            while len(candidates) < max_candidates:
                current_size = min(page_size, max_candidates - len(candidates))
                page = await asyncio.to_thread(
                    CandidateRepository.load_page,
                    department_id,
                    statuses,
                    current_size,
                    offset,
                )
                candidates.extend(page)
                offset += len(page)
                if len(page) < current_size:
                    break
            self._candidate_entries[key] = candidates
            return candidates

    def fuzzy_search_cached(
        self, query: str, department_id: str, limit: int
    ) -> List[Dict[str, Any]]:
        candidates = self._candidate_entries.get(self._key(department_id))
        if candidates is None:
            return []
        return self._rank_fuzzy(query, department_id, candidates, limit)

    async def fuzzy_search(
        self, query: str, department_id: str, limit: int
    ) -> List[Dict[str, Any]]:
        candidates = await self.get_candidates(department_id)
        return self._rank_fuzzy(query, department_id, candidates, limit)

    @staticmethod
    def _rank_fuzzy(
        query: str,
        department_id: str,
        candidates: Sequence[Dict[str, Any]],
        limit: int,
    ) -> List[Dict[str, Any]]:
        valid_statuses = set(allowed_statuses())
        ranked = [
            {**candidate, "score": fuzzy_relevance_score(query, str(candidate.get("content", "")))}
            for candidate in candidates
            if candidate.get("department_id") == department_id
            and str(candidate.get("status", "")).lower() in valid_statuses
        ]
        ranked = [candidate for candidate in ranked if candidate["score"] > 0]
        ranked.sort(key=lambda item: (-item["score"], item.get("step_number") or 0))
        return ranked[:limit]

    async def rebuild(self, department_id: str) -> SemanticIndexEntry:
        key = self._key(department_id)
        candidates = await self.get_candidates(department_id)
        page_size = max(1, settings.LOCAL_AI_CANDIDATE_LIMIT)
        embeddings: List[List[float]] = []
        for start in range(0, len(candidates), page_size):
            batch = candidates[start : start + page_size]
            embeddings.extend(
                await self.provider.embed([str(candidate["content"]) for candidate in batch])
            )
        entry = SemanticIndexEntry(candidates=candidates, embeddings=embeddings)
        self._entries[key] = entry
        return entry

    async def get_or_rebuild(self, department_id: str) -> SemanticIndexEntry:
        key = self._key(department_id)
        entry = self._entries.get(key)
        if entry is not None:
            return entry
        return await self.rebuild(department_id)

    async def search(self, query: str, department_id: str, limit: int) -> List[Dict[str, Any]]:
        entry = await self.get_or_rebuild(department_id)
        if not entry.candidates:
            return []
        query_vectors = await self.provider.embed([query])
        query_vector = query_vectors[0]
        ranked: List[Dict[str, Any]] = []
        valid_statuses = set(allowed_statuses())
        for candidate, vector in zip(entry.candidates, entry.embeddings):
            # Defense in depth after retrieval and before returning any evidence.
            if candidate.get("department_id") != department_id:
                continue
            if str(candidate.get("status", "")).lower() not in valid_statuses:
                continue
            score = cosine_similarity(query_vector, vector)
            if score >= settings.LOCAL_AI_MIN_SIMILARITY:
                ranked.append({**candidate, "score": round(float(score), 6)})
        ranked.sort(key=lambda item: item["score"], reverse=True)
        return ranked[:limit]


class SqlLexicalRetrievalProvider:
    """Deterministic token-aware Snowflake fallback, scoped before retrieval."""

    async def search(self, query: str, department_id: str, limit: int) -> List[Dict[str, Any]]:
        terms = search_terms(query)
        if not terms:
            return []
        statuses = allowed_statuses()
        status_placeholders = ", ".join(["%s"] * len(statuses))
        score_parts = ["IFF(LOWER(sm.search_content) LIKE %s, 1, 0)" for _ in terms]
        where_parts = ["LOWER(sm.search_content) LIKE %s" for _ in terms]
        # Long natural-language questions contain contextual terms that should
        # not dilute several strong lexical matches below the safety gate.
        # One incidental match in a long query still scores at most 0.25.
        relevance_term_count = min(len(terms), 4)
        score_expression = (
            f"LEAST(1.0, (({' + '.join(score_parts)}) / {relevance_term_count}.0))"
        )
        sql = f"""
            SELECT sm.id AS chunk_id,
                   w.id AS document_id,
                   w.title AS document_title,
                   wv.id AS workflow_version_id,
                   wv.version_number,
                   s.id AS state_id,
                   s.ordinal_index AS step_number,
                   s.title AS step_title,
                   sm.search_content AS content,
                   sm.department_id,
                   LOWER(wv.status) AS status,
                   {score_expression} AS score
            FROM WORKMATE_AI.KNOWLEDGE_STUDIO.workflow_search_metadata sm
            JOIN WORKMATE_AI.KNOWLEDGE_STUDIO.workflow_versions wv
              ON sm.workflow_version_id = wv.id
            JOIN WORKMATE_AI.KNOWLEDGE_STUDIO.workflows w
              ON wv.workflow_id = w.id
            JOIN WORKMATE_AI.KNOWLEDGE_STUDIO.workflow_states s
              ON sm.state_id = s.id
            WHERE LOWER(wv.status) IN ({status_placeholders})
              AND LOWER(sm.status) = 'published'
              AND sm.department_id = %s
              AND w.department_id = %s
              AND wv.version_number = (
                  SELECT MAX(candidate_version.version_number)
                  FROM WORKMATE_AI.KNOWLEDGE_STUDIO.workflow_versions candidate_version
                  WHERE candidate_version.workflow_id = wv.workflow_id
                    AND LOWER(candidate_version.status) IN ({status_placeholders})
              )
              AND ({' OR '.join(where_parts)})
            ORDER BY score DESC, s.ordinal_index ASC
            LIMIT %s
        """
        patterns = [f"%{term}%" for term in terms]
        params: List[Any] = [
            *patterns,
            *statuses,
            department_id,
            department_id,
            *statuses,
            *patterns,
            limit,
        ]

        def execute() -> List[Dict[str, Any]]:
            with get_snowflake_connection() as connection:
                with connection.cursor() as cursor:
                    cursor.execute(sql, params)
                    rows = cursor.fetchall()
                    columns = [column[0].lower() for column in cursor.description]
                    return [dict(zip(columns, row)) for row in rows]

        try:
            results = await asyncio.to_thread(execute)
        except Exception as exc:
            logger.error("Scoped SQL retrieval failed: %s", type(exc).__name__)
            raise WorkMateException(message="Copilot retrieval failed.") from exc
        valid_statuses = set(statuses)
        return [
            item
            for item in results
            if item.get("department_id") == department_id
            and str(item.get("status", "")).lower() in valid_statuses
        ]
