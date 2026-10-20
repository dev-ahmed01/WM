"""Phase 12 metric arithmetic, privacy and exact citation provenance tests."""
import json
from argparse import Namespace

import pytest

from app.models.copilot import Citation
from evals.warehouse_acceptance import aggregate, validate_manifest, verify_citation, run


def test_manifest_rejects_bad_labels_duplicates_and_oversized_questions():
    valid = {"id":"a", "language":"en","question":"What seal?", "department_id":"ops",
             "expected_document_id":None}
    assert validate_manifest([valid])[0] == valid
    with pytest.raises(ValueError, match="unique"):
        validate_manifest([valid, valid])
    with pytest.raises(ValueError, match="en, hi"):
        validate_manifest([dict(valid, language="fr")])
    with pytest.raises(ValueError, match="Invalid department"):
        validate_manifest([dict(valid, department_id="../cross")])
    with pytest.raises(ValueError, match="Negative"):
        validate_manifest([dict(valid, expected_evidence="Ignore instructions")])
    with pytest.raises(ValueError, match="300"):
        validate_manifest([dict(valid, question="x"*301)])


def test_aggregates_are_redacted_and_not_speech_accuracy():
    results = [
        {"language":"en","expected":True,"top1":True,"recall5":True,
         "correct_document":True,"gold_evidence":True,"abstained":False,
         "citations":1,"valid_citations":1,"invalid_citations":0,
         "latency_ms":23.0,"private_question":"this must not be emitted"},
        {"language":"hinglish","expected":False,"top1":False,"recall5":False,
         "correct_document":False,"gold_evidence":False,"abstained":True,
         "citations":0,"valid_citations":0,"invalid_citations":0,
         "latency_ms":30.0,"private_question":"another secret"},
    ]
    report = aggregate(results, "synthetic_evaluator_unit_only")
    assert report["overall"]["top1_recall"] == 1.0
    assert report["overall"]["citation_precision"] == 1.0
    assert report["overall"]["correct_abstention_rate"] == 1.0
    assert report["by_language"]["hinglish"]["positive"] == 0
    assert report["by_language"]["hinglish"]["recall_at_5"] is None
    assert "private_question" not in json.dumps(report)
    assert "another secret" not in json.dumps(report)


def test_verify_citation_checks_exact_offsets_source_and_approval(monkeypatch):
    from app.repositories.reference_document_repository import ReferenceDocumentRepository
    monkeypatch.setattr(ReferenceDocumentRepository, "get_document",
                        lambda *_: {"status":"APPROVED"})
    monkeypatch.setattr(ReferenceDocumentRepository, "read_chunks", lambda *_: [
        {"id":"c1","start_offset":10,"end_offset":29,"content":"Inspect seal at dock"}
    ])
    citation = Citation(document_id="d1", document_title="Receiving", version_number=None,
                        chunk_id="c1", excerpt="Inspect seal", source_type="reference",
                        section_anchor="excerpt 1, chars 10–22")
    assert verify_citation(citation, "ops")
    assert not verify_citation(citation.model_copy(update={"section_anchor":"excerpt 1, chars 11–23"}), "ops")
    assert not verify_citation(citation.model_copy(update={"excerpt":"Ignore safety"}), "ops")
    assert not verify_citation(citation.model_copy(update={"source_type":"workflow"}), "ops")
    monkeypatch.setattr(ReferenceDocumentRepository, "get_document",
                        lambda *_: {"status":"ARCHIVED"})
    assert not verify_citation(citation, "ops")


def test_live_runner_opt_in_and_label_count(tmp_path, monkeypatch):
    path = tmp_path / "label.json"
    path.write_text(json.dumps([{"id":"e1","language":"en","question":"security seal",
                "department_id":"receiving","expected_document_id":None}]))
    monkeypatch.delenv("WORKMATE_EVAL_LIVE", raising=False)
    with pytest.raises(RuntimeError, match="WORKMATE_EVAL_LIVE"):
        run(Namespace(manifest=path,min_cases=0))
    monkeypatch.setenv("WORKMATE_EVAL_LIVE", "1")
    with pytest.raises(ValueError, match="cohort"):
        run(Namespace(manifest=path,min_cases=100))
    with pytest.raises(ValueError, match="representation"):
        run(Namespace(manifest=path,min_cases=0,min_per_language=1,min_negative=0))
    with pytest.raises(ValueError, match="negative"):
        run(Namespace(manifest=path,min_cases=0,min_per_language=0,min_negative=2))
