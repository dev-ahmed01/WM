"""Executable smoke evaluation for the real Copilot validation gate."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.services.validation import CANONICAL_FALLBACK, ResponseValidationService  # noqa: E402


SOURCE = {
    "chunk_id": "eval_chunk",
    "document_id": "eval_document",
    "document_title": "Receiving SOP",
    "version_number": 1,
    "department_id": "dept_inbound",
    "content": "Inspect the shipment seal before unloading.",
    "score": 1.0,
}


def run() -> int:
    grounded, _ = ResponseValidationService.validate_response(
        "Inspect the shipment seal before unloading.",
        [SOURCE],
        "employee",
        "dept_inbound",
    )
    hallucinated, _ = ResponseValidationService.validate_response(
        "Disable the fire alarm and remove the pressure sensor.",
        [SOURCE],
        "employee",
        "dept_inbound",
    )
    cross_department, _ = ResponseValidationService.validate_response(
        "Inspect the shipment seal before unloading.",
        [SOURCE],
        "employee",
        "dept_outbound",
    )
    results = {
        "grounded_answer_accepted": grounded.is_grounded and len(grounded.citations) == 1,
        "hallucination_blocked": hallucinated.answer == CANONICAL_FALLBACK,
        "cross_department_blocked": cross_department.answer == CANONICAL_FALLBACK,
    }
    print(json.dumps(results, indent=2, sort_keys=True))
    return 0 if all(results.values()) else 1


if __name__ == "__main__":
    raise SystemExit(run())
