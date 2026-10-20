"""Reference hybrid retrieval: approval gates, rerank math, multilingual support and fallback."""
from unittest.mock import AsyncMock
import pytest

from app.repositories.reference_document_repository import ReferenceDocumentRepository
from app.services.reference_retrieval import (
    ReferenceRetrievalService, authorized, lexical_score, rerank_lexical, tokens,
)
from app.services.reference_answer import ReferenceAnswerService


def source(chunk_id="c1", excerpt="If the carton is damaged, inspect the seal and quarantine the parcel.",
           department_id="receiving", status="APPROVED"):
    return {
        "document_id": f"doc_{chunk_id}", "document_title": "Receiving SOP",
        "department_id": department_id, "chunk_id": chunk_id,
        "excerpt": excerpt, "start_offset": 0, "end_offset": len(excerpt),
        "chunk_index": 0, "status": status, "match_score": 0.8,
    }


def test_whole_token_not_substring_and_warehouse_synonyms():
    assert lexical_score("broken box", "Damaged carton received") == 1.0
    assert lexical_score("seal", "The sealed crate") == 0.0
    assert lexical_score("alarm bypass machine", "Inspect the carton seal") == 0.0


def test_hindi_combining_marks_are_preserved():
    terms = tokens("पैकेज क्षतिग्रस्त सील")
    assert "पैकेज" in terms
    assert "क्षतिग्रस्त" in terms
    assert "सील" in terms
    assert lexical_score("पैकेज क्षतिग्रस्त", "Damaged carton") == 1.0


def test_lexical_rank_never_exposes_drafts_or_other_departments():
    documents = [
        source("wrong", "Damaged carton", department_id="payroll"),
        source("draft", "Damaged carton", status="DRAFT"),
        source("valid", "If a damaged carton is identified, inspect the seal and notify a supervisor."),
    ]
    result = rerank_lexical("damaged carton", documents, "receiving")
    assert len(result) == 1
    assert result[0]["chunk_id"] == "valid"


@pytest.mark.asyncio
async def test_live_approval_is_rechecked_on_each_query(monkeypatch):
    state = {"status": "APPROVED", "calls": 0}
    def lexical(_query, _department, *, limit):
        state["calls"] += 1
        return [source(status=state["status"])]
    def pool(_department, *, limit):
        return [source(status=state["status"])]
    monkeypatch.setattr(ReferenceDocumentRepository, "search_approved", lexical)
    monkeypatch.setattr(ReferenceDocumentRepository, "list_approved_candidates", pool)
    monkeypatch.setattr("app.services.reference_retrieval.settings.REFERENCE_HYBRID_ENABLED", False)
    first = await ReferenceRetrievalService.search("damaged carton", "receiving")
    state["status"] = "ARCHIVED"
    second = await ReferenceRetrievalService.search("damaged carton", "receiving")
    assert first and not second and state["calls"] == 2


@pytest.mark.asyncio
async def test_semantic_ranking_is_bounded_and_cannot_embed_disallowed_sources(monkeypatch):
    valid1 = source("valid1", "The carton requires seal inspection on arrival.")
    valid2 = source("valid2", "A damaged carton should be quarantined after inspection.")
    disallowed = source("private", "A carton belongs to payroll.", department_id="payroll")
    monkeypatch.setattr(ReferenceDocumentRepository, "search_approved", lambda *_a, **_k: [valid1, disallowed])
    monkeypatch.setattr(ReferenceDocumentRepository, "list_approved_candidates", lambda *_a, **_k: [valid2, disallowed])
    monkeypatch.setattr("app.services.reference_retrieval.settings.REFERENCE_HYBRID_ENABLED", True)
    monkeypatch.setattr("app.services.reference_retrieval.settings.LOCAL_AI_ENABLED", True)
    embedded = []
    async def embeddings(values):
        embedded.extend(values)
        return [[1., 0.]] + [[1., 0.] if "quarantined" in item else [0., 1.] for item in values[1:]]
    monkeypatch.setattr(ReferenceRetrievalService.provider, "embed", embeddings)
    result = await ReferenceRetrievalService.search("damaged carton", "receiving")
    assert all(item["department_id"] == "receiving" for item in result)
    assert all(item["status"] == "APPROVED" for item in result)
    assert not any("payroll" in item for item in embedded)
    assert result[0]["chunk_id"] == "valid2"
    assert result[0]["retrieval_method"] == "hybrid"


@pytest.mark.asyncio
async def test_local_embedding_timeout_falls_back_to_lexical(monkeypatch):
    monkeypatch.setattr(ReferenceDocumentRepository, "search_approved", lambda *_a, **_k: [source()])
    monkeypatch.setattr(ReferenceDocumentRepository, "list_approved_candidates", lambda *_a, **_k: [])
    monkeypatch.setattr("app.services.reference_retrieval.settings.REFERENCE_HYBRID_ENABLED", True)
    monkeypatch.setattr("app.services.reference_retrieval.settings.LOCAL_AI_ENABLED", True)
    async def error(_):
        raise TimeoutError("local offline")
    monkeypatch.setattr(ReferenceRetrievalService.provider, "embed", error)
    results = await ReferenceRetrievalService.search("damaged carton", "receiving")
    assert len(results) == 1 and results[0]["retrieval_method"] == "lexical"


def test_semantic_only_never_fabricates_an_authoritative_workflow_step():
    result = ReferenceAnswerService.validate_reference_answer(
        "override alarm bypass safeguards",
        [source(excerpt="Inspect damaged cartons and verify the seal.") | {"semantic_score": 0.99, "rank_score": 0.99}],
        "receiving",
    )
    assert result.requires_escalation
    assert not result.is_grounded
    assert result.citations == []


def test_paraphrased_safe_reference_still_requires_exact_verbatim_quote():
    text = "Damaged cartons must be quarantined and reported to the supervisor."
    result = ReferenceAnswerService.validate_reference_answer(
        "broken box quarantine", [source(excerpt=text)], "receiving"
    )
    assert result.is_grounded
    assert result.citations[0].excerpt in text
    assert "recorded workflow" in result.answer


def test_english_questions_prefer_english_evidence_on_bilingual_ties():
    english = source("english", "If a carton is damaged, inspect the seal and quarantine the parcel.")
    hindi = source("hindi", "यदि पैकेज क्षतिग्रस्त है तो सील की जांच करें और माल अलग रखें।")
    ranked = rerank_lexical("broken box seal quarantine", [hindi, english], "receiving")
    assert ranked[0]["chunk_id"] == "english"
    validated = ReferenceAnswerService.validate_reference_answer(
        "broken box seal quarantine", ranked, "receiving"
    )
    assert validated.is_grounded
    assert validated.citations[0].chunk_id == "english"
