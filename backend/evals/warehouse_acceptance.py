"""Privacy-minimizing acceptance harness for real PostgreSQL-approved SOP references.

Use an independently labeled PRIVATE manifest with real warehouse operators'
questions. The repo contains only tests and a synthetic practice dataset;
do not publish raw questions, private sources, or generated answers.

Live:
  WORKMATE_EVAL_LIVE=1 PYTHONPATH=backend python backend/evals/warehouse_acceptance.py \
    --manifest /private/warehouse_gold.json --output /private/aggregate.json

The evaluator reads current PostgreSQL approved references via the exact
Copilot retrieval/validation services. It never creates or changes workflows.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import re
import statistics
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable

from app.core.config import settings
from app.repositories.reference_document_repository import ReferenceDocumentRepository
from app.services.reference_answer import ReferenceAnswerService
from app.services.reference_retrieval import ReferenceRetrievalService

LANGUAGES = frozenset({"en", "hi", "hinglish"})
_CITATION_ANCHOR = re.compile(r"excerpt \d+, chars (\d+)–(\d+)$")


def validate_manifest(rows: Any) -> list[dict[str, Any]]:
    if not isinstance(rows, list) or not rows or len(rows) > 1000:
        raise ValueError("Expected between 1 and 1000 independently labeled cases")
    ids: set[str] = set()
    safe: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("Each case must be a mapping")
        identifier = row.get("id")
        language = row.get("language")
        query = row.get("question")
        dept = row.get("department_id")
        expected = row.get("expected_document_id")
        label = row.get("expected_evidence", "")
        if (not isinstance(identifier, str) or not identifier.strip()
                or len(identifier) > 80 or identifier in ids):
            raise ValueError("Cases need unique bounded IDs")
        ids.add(identifier)
        if language not in LANGUAGES:
            raise ValueError("Language must be en, hi or hinglish")
        if not isinstance(query, str) or not 2 <= len(query.strip()) <= 300:
            raise ValueError("Question must contain 2-300 characters")
        if not isinstance(dept, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", dept):
            raise ValueError("Invalid department identifier")
        if expected is not None and (not isinstance(expected, str) or len(expected) > 100):
            raise ValueError("expected_document_id must be string or null")
        if not isinstance(label, str) or len(label) > 500:
            raise ValueError("expected_evidence must be a bounded excerpt")
        if expected is None and label:
            raise ValueError("Negative cases cannot include expected_evidence")
        safe.append(dict(row))
    return safe


def _p95(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return round(ordered[math.ceil(0.95 * len(ordered)) - 1], 2)


def aggregate(results: list[dict[str, Any]], provenance: str) -> dict[str, Any]:
    if not results:
        raise ValueError("No evaluation results")
    def summary(items: list[dict[str, Any]]) -> dict[str, Any]:
        positive = [r for r in items if r["expected"]]
        negative = [r for r in items if not r["expected"]]
        citations = [r for r in items if r["citations"]]
        def ratio(n: int, d: int) -> float | None:
            return round(n / d, 4) if d else None
        return {
            "cases": len(items), "positive": len(positive), "negative": len(negative),
            "top1_recall": ratio(sum(r["top1"] for r in positive), len(positive)),
            "recall_at_5": ratio(sum(r["recall5"] for r in positive), len(positive)),
            "correct_document_rate": ratio(sum(r["correct_document"] for r in positive), len(positive)),
            "answer_evidence_rate": ratio(sum(r["gold_evidence"] for r in positive), len(positive)),
            "correct_abstention_rate": ratio(sum(r["abstained"] for r in negative), len(negative)),
            "false_answer_cases": sum(not r["abstained"] for r in negative),
            "citation_precision": ratio(sum(r["valid_citations"] for r in items),
                                        sum(r["citations"] for r in items)),
            "invalid_citation_cases": sum(r["invalid_citations"] > 0 for r in items),
            "latency_p50_ms": round(statistics.median(r["latency_ms"] for r in items), 2),
            "latency_p95_ms": _p95([r["latency_ms"] for r in items]),
        }
    groups = defaultdict(list)
    for result in results:
        groups[result["language"]].append(result)
    return {
        "provenance": provenance,
        "overall": summary(results),
        "by_language": {lang: summary(groups[lang]) for lang in sorted(groups)},
        "privacy": "Metrics only; raw questions, approved document text and answers are never included.",
        "limitations": "Verified spans/labels measure extractive support, not independent factual truth or warehouse process safety.",
    }


def verify_citation(citation: Any, department_id: str) -> bool:
    if citation.source_type != "reference":
        return False
    document = ReferenceDocumentRepository.get_document(citation.document_id, department_id)
    if not document or document.get("status") != "APPROVED":
        return False
    chunks = ReferenceDocumentRepository.read_chunks(citation.document_id, department_id)
    source = next((c for c in chunks if c["id"] == citation.chunk_id), None)
    if not source:
        return False
    anchor = _CITATION_ANCHOR.fullmatch(citation.section_anchor or "")
    if not anchor:
        return False
    start, end = (int(v) for v in anchor.groups())
    position = start - source["start_offset"]
    quote = citation.excerpt
    return bool(
        isinstance(quote, str) and quote.strip()
        and 0 <= position and start < end
        and end - start == len(quote)
        and end <= source["end_offset"]
        and source["content"][position:position + len(quote)] == quote
    )


async def evaluate_live(rows: list[dict[str, Any]]) -> dict[str, Any]:
    from starlette.concurrency import run_in_threadpool
    results = []
    for case in validate_manifest(rows):
        start = time.perf_counter()
        ranked = await ReferenceRetrievalService.search(
            case["question"], case["department_id"], limit=20,
        )
        answer = ReferenceAnswerService.validate_reference_answer(
            case["question"], ranked, case["department_id"],
        )
        valid = [
            await run_in_threadpool(verify_citation, citation, case["department_id"])
            for citation in answer.citations
        ]
        elapsed_ms = (time.perf_counter() - start) * 1000
        expected = case["expected_document_id"]
        citations = answer.citations
        correct = bool(expected and citations and citations[0].document_id == expected and all(valid))
        gold = case.get("expected_evidence", "")
        evidence = bool(correct and (not gold or any(
            gold in citation.excerpt for citation in citations
        )))
        results.append({
            "language": case["language"],
            "expected": bool(expected),
            "top1": bool(expected and ranked and ranked[0]["document_id"] == expected),
            "recall5": bool(expected and any(c["document_id"] == expected for c in ranked[:5])),
            "correct_document": correct,
            "gold_evidence": evidence,
            "abstained": bool(answer.requires_escalation and not citations and not answer.is_grounded),
            "citations": len(citations),
            "valid_citations": sum(valid),
            "invalid_citations": len(citations) - sum(valid),
            "latency_ms": round(elapsed_ms, 2),
        })
    return aggregate(results, "live_postgres_user_labeled")


def run(args: argparse.Namespace) -> dict[str, Any]:
    if os.environ.get("WORKMATE_EVAL_LIVE") != "1":
        raise RuntimeError("Explicit WORKMATE_EVAL_LIVE=1 required for database evaluation")
    rows = validate_manifest(json.loads(args.manifest.read_text(encoding="utf-8")))
    if args.min_cases and len(rows) < args.min_cases:
        raise ValueError("Manifest smaller than user-specified acceptance cohort")
    return asyncio.run(evaluate_live(rows))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Evaluate real current approved PostgreSQL references")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, help="Optional aggregate-only report; keep private")
    parser.add_argument("--min-cases", type=int, default=0)
    parser.add_argument("--fail-on-invalid", action="store_true")
    parsed = parser.parse_args()
    report = run(parsed)
    serialized = json.dumps(report, ensure_ascii=False, indent=2)
    if parsed.output:
        parsed.output.write_text(serialized + "\n", encoding="utf-8")
    print(serialized)
    if parsed.fail_on_invalid and (report["overall"]["invalid_citation_cases"] or
                                   report["overall"]["false_answer_cases"]):
        raise SystemExit(1)
