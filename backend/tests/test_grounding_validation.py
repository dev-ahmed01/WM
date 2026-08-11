"""Grounding and citation validation cannot be satisfied by retrieval alone."""

from app.integrations.ai_provider import GeneratedAnswer
from app.services.validation import CANONICAL_FALLBACK, ResponseValidationService


def chunk(**overrides):
    value = {
        "chunk_id": "chunk-1",
        "document_id": "doc-1",
        "document_title": "Receiving SOP",
        "version_number": 2,
        "step_number": 3,
        "department_id": "dept_ops",
        "status": "published",
        "content": "Inspect the security seal before unloading the shipment.",
        "score": 0.95,
    }
    value.update(overrides)
    return value


def validate(generated, chunks=None, department="dept_ops"):
    return ResponseValidationService.validate_response(
        raw_response=generated,
        retrieved_chunks=chunks if chunks is not None else [chunk()],
        user_role="employee",
        user_department_id=department,
    )


def test_valid_cited_paraphrase_is_accepted():
    validated, escalated = validate(
        GeneratedAnswer("Before unloading, inspect the shipment security seal.", ["chunk-1"], "test")
    )

    assert escalated is False
    assert validated.is_grounded is True
    assert validated.confidence_score >= 0.70
    assert validated.citations[0].chunk_id == "chunk-1"


def test_retrieved_chunk_does_not_validate_unrelated_instruction():
    validated, escalated = validate(
        GeneratedAnswer("Disable the fire alarm and open every loading door.", ["chunk-1"], "test")
    )

    assert escalated is True
    assert validated.answer.startswith("Verified extract")
    assert "Disable the fire alarm" not in validated.answer


def test_weak_semantic_match_produces_canonical_fallback():
    validated, escalated = validate(
        GeneratedAnswer("Inspect the shipment seal.", ["chunk-1"], "test"),
        [chunk(score=0.51)],
    )

    assert escalated is True
    assert validated.answer == CANONICAL_FALLBACK
    assert validated.citations == []
    assert validated.is_grounded is False
    assert validated.confidence_score == 0.0


def test_fabricated_source_id_is_rejected():
    validated, escalated = validate(
        GeneratedAnswer("Inspect the security seal.", ["fabricated"], "test")
    )

    assert escalated is True
    assert all(citation.chunk_id != "fabricated" for citation in validated.citations)


def test_missing_source_identifier_is_rejected():
    validated, escalated = validate(
        GeneratedAnswer("Inspect the security seal.", [], "test")
    )

    assert escalated is True
    assert validated.answer.startswith("Verified extract")


def test_missing_citation_metadata_produces_canonical_fallback():
    incomplete = chunk(document_id=None)

    validated, escalated = validate(
        GeneratedAnswer("Inspect the security seal.", ["chunk-1"], "test"), [incomplete]
    )

    assert escalated is True
    assert validated.answer == CANONICAL_FALLBACK
    assert validated.citations == []


def test_cross_department_chunk_is_rejected_even_for_valid_source_id():
    validated, escalated = validate(
        GeneratedAnswer("Inspect the security seal.", ["chunk-1"], "test"),
        [chunk(department_id="dept_hr")],
    )

    assert escalated is True
    assert validated.answer == CANONICAL_FALLBACK


def test_draft_and_archived_chunks_are_rejected(monkeypatch):
    monkeypatch.setattr(
        "app.services.validation.settings.COPILOT_ALLOWED_KNOWLEDGE_STATUSES", "published"
    )
    for status in ("draft", "archived"):
        validated, escalated = validate(
            GeneratedAnswer("Inspect the security seal.", ["chunk-1"], "test"),
            [chunk(status=status)],
        )
        assert escalated is True
        assert validated.answer == CANONICAL_FALLBACK


def test_missing_retrieval_score_cannot_fabricate_confidence():
    incomplete = chunk()
    incomplete.pop("score")

    validated, escalated = validate(
        GeneratedAnswer("Inspect the security seal.", ["chunk-1"], "test"), [incomplete]
    )

    assert escalated is True
    assert validated.confidence_score == 0.0
