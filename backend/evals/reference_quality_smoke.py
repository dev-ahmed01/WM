"""Offline, deterministic reference QA smoke benchmark.

The included labels are synthetic and must NOT be treated as a production
accuracy measurement. The benchmark intentionally does not call Snowflake or
Ollama. It is a regression gate for permissions, abstention, citation integrity
and token-based retrieval on a fixed set of operational questions.
"""
from __future__ import annotations

import json
import statistics
import time
from pathlib import Path
from typing import Any

from app.services.reference_answer import ReferenceAnswerService
from app.services.reference_retrieval import rerank_lexical

FIXTURE = Path(__file__).parent / "fixtures" / "reference_quality_smoke.json"


def evaluate(cases: list[dict[str, Any]], sources: list[dict[str, Any]]) -> dict[str, Any]:
    positive = negative = top1_hits = recall3_hits = correct_abstentions = 0
    citation_checks = 0
    wrong_citations = 0
    durations = []
    errors = []
    for case in cases:
        query, department = case["question"], case["department_id"]
        expected = case["expected_document_id"]
        start = time.perf_counter()
        ranking = rerank_lexical(query, sources, department, limit=10)
        answer = ReferenceAnswerService.validate_reference_answer(query, ranking, department)
        durations.append((time.perf_counter() - start) * 1000)
        if expected is None:
            negative += 1
            if answer.requires_escalation and not answer.citations:
                correct_abstentions += 1
            else:
                errors.append({"query": query, "kind": "false_positive"})
        else:
            positive += 1
            top1_hits += bool(ranking and ranking[0]["document_id"] == expected)
            recall3_hits += any(row["document_id"] == expected for row in ranking[:3])
            if not answer.citations or answer.citations[0].document_id != expected:
                errors.append({"query": query, "kind": "missing_or_wrong_citation"})
        for citation in answer.citations:
            citation_checks += 1
            original = next(
                (s for s in sources if s["chunk_id"] == citation.chunk_id
                 and s["document_id"] == citation.document_id
                 and s["status"] == "APPROVED" and s["department_id"] == department),
                None,
            )
            if original is None or citation.excerpt not in original["excerpt"]:
                wrong_citations += 1
                errors.append({"query": query, "kind": "invalid_source_span"})
    count = len(durations)
    p95 = sorted(durations)[min(count - 1, int(count * 0.95))] if count else 0
    return {
        "questions": len(cases),
        "positive": positive,
        "negative": negative,
        "lexical_top1_accuracy": round(top1_hits / positive, 3) if positive else 0,
        "lexical_recall_at_3": round(recall3_hits / positive, 3) if positive else 0,
        "correct_abstention_rate": round(correct_abstentions / negative, 3) if negative else 0,
        "citation_span_integrity": round((citation_checks - wrong_citations) / citation_checks, 3) if citation_checks else None,
        "offline_p95_latency_ms": round(p95, 2),
        "failures": errors,
        "disclaimer": "Synthetic offline fixture: not a live semantic, Snowflake, Hindi voice, or factual correctness evaluation.",
    }


def run_fixture(path: Path = FIXTURE) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return evaluate(data["cases"], data["sources"])


if __name__ == "__main__":
    print(json.dumps(run_fixture(), ensure_ascii=False, indent=2))
