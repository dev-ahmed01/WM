"""Grounded query-to-SOP memory built only from employee-confirmed selections."""

import re
import time
from typing import Any, Dict, Sequence

from app.core.text_matching import fuzzy_relevance_score, search_terms
from app.repositories.query_resolution_repository import QueryResolutionRepository


def normalized_query_key(query: str) -> str:
    terms = search_terms(query)
    if terms:
        return " ".join(terms)
    return " ".join(re.findall(r"[a-z0-9]+", (query or "").casefold()))[:500]


class QueryResolutionMemoryService:
    _cache: dict[str, tuple[float, list[Dict[str, Any]]]] = {}
    _cache_seconds = 60.0

    @classmethod
    def invalidate(cls, department_id: str) -> None:
        cls._cache.pop(department_id, None)

    @classmethod
    def _confirmed(cls, department_id: str) -> list[Dict[str, Any]]:
        cached = cls._cache.get(department_id)
        now = time.monotonic()
        if cached and now - cached[0] < cls._cache_seconds:
            return cached[1]
        rows = QueryResolutionRepository.list_confirmed(department_id)
        cls._cache[department_id] = (now, rows)
        return rows

    @classmethod
    def match(
        cls,
        query: str,
        department_id: str,
        catalog: Sequence[Dict[str, Any]],
    ) -> Dict[str, Any] | None:
        """Return a still-published SOP only for a strong, unique learned match."""
        query_key = normalized_query_key(query)
        if not query_key or not catalog:
            return None
        catalog_by_version = {
            str(item.get("workflow_version_id")): item for item in catalog
        }
        ranked: list[tuple[float, Dict[str, Any]]] = []
        for memory in cls._confirmed(department_id):
            workflow = catalog_by_version.get(str(memory.get("workflow_version_id")))
            if not workflow:
                continue
            stored_key = str(memory.get("normalized_query") or "")
            score = 1.0 if query_key == stored_key else fuzzy_relevance_score(
                query_key,
                " ".join(
                    str(memory.get(field) or "")
                    for field in ("normalized_query", "original_query", "translated_query")
                ),
            )
            ranked.append((score, {**workflow, "memory_id": memory["id"]}))
        ranked.sort(key=lambda item: item[0], reverse=True)
        if not ranked or ranked[0][0] < 0.75:
            return None
        runner_up = ranked[1][0] if len(ranked) > 1 else 0.0
        if runner_up >= 0.75 and ranked[0][0] - runner_up < 0.12:
            return None
        score, workflow = ranked[0]
        QueryResolutionRepository.record_hit(str(workflow["memory_id"]))
        return {**workflow, "match_score": score, "matched_from_memory": True}
