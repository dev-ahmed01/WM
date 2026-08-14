"""Executable smoke evaluation for the real Copilot validation gate."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.integrations.ai_provider import GeneratedAnswer  # noqa: E402
from app.services.validation import (  # noqa: E402
    CANONICAL_FALLBACK,
    ResponseValidationService,
)


SOURCE = {
    "chunk_id": "eval_chunk",
    "document_id": "eval_document",
    "document_title": "Receiving SOP",
    "version_number": 1,
    "step_number": 1,
    "department_id": "dept_inbound",
    "status": "published",
    "content": "Inspect the shipment seal before unloading.",
    "score": 1.0,
}


def run() -> int:
    grounded, _ = ResponseValidationService.validate_response(
        GeneratedAnswer(
            answer="Inspect the shipment seal before unloading.",
            source_ids=["eval_chunk"],
            provider="evaluation",
        ),
        [SOURCE],
        "employee",
        "dept_inbound",
    )
    hallucinated, _ = ResponseValidationService.validate_response(
        GeneratedAnswer(
            answer="Disable the fire alarm and remove the pressure sensor.",
            source_ids=["eval_chunk"],
            provider="evaluation",
        ),
        [SOURCE],
        "employee",
        "dept_inbound",
    )
    cross_department, _ = ResponseValidationService.validate_response(
        GeneratedAnswer(
            answer="Inspect the shipment seal before unloading.",
            source_ids=["eval_chunk"],
            provider="evaluation",
        ),
        [SOURCE],
        "employee",
        "dept_outbound",
    )
    results = {
        "grounded_answer_accepted": grounded.is_grounded and len(grounded.citations) == 1,
        "hallucination_blocked": (
            hallucinated.requires_escalation
            and "fire alarm" not in hallucinated.answer.casefold()
        ),
        "cross_department_blocked": cross_department.answer == CANONICAL_FALLBACK,
    }
    print(json.dumps(results, indent=2, sort_keys=True))
    return 0 if all(results.values()) else 1


if __name__ == "__main__":
    raise SystemExit(run())
