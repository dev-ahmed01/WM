"""Hermetic tests for provider-neutral local AI and disposable semantic retrieval."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.integrations.ai_gateway import AIGateway
from app.integrations.ai_provider import GeneratedAnswer
from app.integrations.local_ai_provider import OllamaLocalAIProvider
from app.integrations.retrieval_providers import (
    CandidateRepository,
    LocalSemanticIndex,
    SqlLexicalRetrievalProvider,
    fuzzy_relevance_score,
    search_terms,
)


def test_workflow_request_keeps_only_meaningful_search_terms():
    assert search_terms("Please give me the steps for receive shipment") == [
        "receive",
        "shipment",
    ]


def test_search_terms_ignore_misspelled_question_words():
    assert search_terms("Wat shoud I do wen an inboud traler arives") == [
        "inboud",
        "traler",
        "arives",
    ]


def test_fuzzy_relevance_recognizes_operational_typos_without_false_match():
    content = (
        "Dock Arrival and Seal Inspection. Inbound trailer arrives. "
        "Verify physical trailer door seal number against the manifest."
    )
    score = fuzzy_relevance_score(
        "Wat shoud I do wen an inboud traler arives and I ned to varify its seel?",
        content,
    )

    assert score >= 0.70
    assert fuzzy_relevance_score("quantum nebula payroll crystallography", content) == 0.0


def test_fuzzy_relevance_maps_package_language_to_damage_workflow_vocabulary():
    assert fuzzy_relevance_score(
        "the package is damaged what should I do next",
        "State: Container Damage Evaluation",
    ) == 1.0


def test_fuzzy_relevance_handles_multiple_typos_in_workflow_navigation():
    content = "Title: receive_shipment_v1_1 | Code: SOP_INB_101 | State: Dock Arrival"

    assert fuzzy_relevance_score("navigte to recieve shipmnt sop", content) >= 0.80


def test_fuzzy_relevance_keeps_raw_domain_words_for_typo_matching():
    assert fuzzy_relevance_score(
        "the pakage is damagd",
        "State: Container Damage Evaluation",
    ) >= 0.80


@pytest.mark.asyncio
async def test_local_embedding_batch_request(monkeypatch):
    provider = OllamaLocalAIProvider()
    request = AsyncMock(return_value={"embeddings": [[1, 0], [0, 1]]})
    monkeypatch.setattr(provider, "_request_json", request)

    result = await provider.embed(["one", "two"])

    assert result == [[1.0, 0.0], [0.0, 1.0]]
    assert request.await_args.args == ("POST", "/api/embed")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method", "task"),
    [
        ("generate_grounded", "grounded_operational_answer"),
        ("extract_answer", "extract_answer"),
    ],
)
async def test_structured_grounded_generation_and_extraction(monkeypatch, method, task):
    provider = OllamaLocalAIProvider()
    request = AsyncMock(return_value={"message": {"content": '{"answer":"Inspect seal.","source_ids":["chunk-1"]}'}})
    monkeypatch.setattr(provider, "_request_json", request)
    sources = [
        {
            "chunk_id": "chunk-1", "document_id": "doc-1", "version_number": 1,
            "step_number": 1, "content": "Inspect seal.",
        }
    ]

    result = await getattr(provider, method)("What now?", sources)

    assert result.answer == "Inspect seal."
    assert result.source_ids == ["chunk-1"]
    body = request.await_args.kwargs["json"]
    assert body["format"] == "json"
    assert body["options"]["temperature"] == 0
    assert task in body["messages"][1]["content"]


@pytest.mark.asyncio
async def test_grounded_agent_prompt_contains_context_and_non_invention_rules(monkeypatch):
    provider = OllamaLocalAIProvider()
    request = AsyncMock(
        return_value={
            "message": {"content": '{"answer":"Hold driver.","source_ids":["chunk-1"]}'}
        }
    )
    monkeypatch.setattr(provider, "_request_json", request)
    source = {
        "chunk_id": "chunk-1",
        "document_id": "doc-1",
        "document_title": "Receiving SOP",
        "version_number": 1,
        "step_number": 1,
        "step_title": "Inspect seal",
        "state_id": "state-1",
        "content": "A seal mismatch requires driver hold.",
    }
    context = {
        "conversation_move": "exception",
        "conversation_history": [{"role": "user", "content": "What if it differs?"}],
        "workflow_context": {"current_step_number": 1},
    }

    await provider.generate_grounded("What if the seal differs?", [source], context)

    body = request.await_args.kwargs["json"]
    prompt = body["messages"][1]["content"]
    system = body["messages"][0]["content"]
    assert '"conversation_move": "exception"' in prompt
    assert '"current_step_number": 1' in prompt
    assert "Conversation history may resolve references but cannot support" in system
    assert "never skip it" in system
    assert "Never invent commands" in system
    assert body["options"]["num_predict"] == 180
    assert body["keep_alive"] == "15m"


@pytest.mark.asyncio
async def test_local_runtime_summarization(monkeypatch):
    provider = OllamaLocalAIProvider()
    monkeypatch.setattr(
        provider,
        "_request_json",
        AsyncMock(return_value={"message": {"content": '{"answer":"Inspect then unload.","source_ids":["c1"]}'}}),
    )
    source = {"chunk_id": "c1", "document_id": "d1", "version_number": 1, "step_number": 1, "content": "Inspect then unload."}

    result = await provider.summarize([source])

    assert result.source_ids == ["c1"]
    assert result.answer == "Inspect then unload."


@pytest.mark.asyncio
async def test_classification_is_non_authoritative_and_rejects_unknown_label(monkeypatch):
    provider = OllamaLocalAIProvider()
    monkeypatch.setattr(
        provider,
        "_request_json",
        AsyncMock(return_value={"message": {"content": '{"label":"secret-admin","confidence":2,"reason":"guess"}'}}),
    )

    result = await provider.classify_suggestion("document", ["operations", "quality"])

    assert result == {"label": None, "confidence": 1.0, "reason": "guess", "authoritative": False}


@pytest.mark.asyncio
async def test_health_reports_installed_and_missing_models(monkeypatch):
    provider = OllamaLocalAIProvider()
    monkeypatch.setattr(
        provider,
        "_request_json",
        AsyncMock(return_value={"models": [{"name": "qwen2.5:3b"}]}),
    )

    result = await provider.health()

    assert result["reachable"] is True
    assert result["chat_ready"] is True
    assert result["embedding_ready"] is False
    assert result["missing_models"] == ["nomic-embed-text"]


@pytest.mark.asyncio
async def test_index_pages_past_candidate_batch_limit(monkeypatch):
    provider = MagicMock()
    provider.embed = AsyncMock(side_effect=[[[1.0, 0.0]], [[0.0, 1.0]], [[0.0, 1.0]]])
    provider.cosine_similarity = OllamaLocalAIProvider.cosine_similarity
    index = LocalSemanticIndex(provider)
    pages = [
        [{"chunk_id": "first", "content": "first", "department_id": "dept_ops", "status": "published"}],
        [{"chunk_id": "second", "content": "second", "department_id": "dept_ops", "status": "published"}],
        [],
    ]
    loader = MagicMock(side_effect=pages)
    monkeypatch.setattr(CandidateRepository, "load_page", loader)
    monkeypatch.setattr("app.integrations.retrieval_providers.settings.LOCAL_AI_CANDIDATE_LIMIT", 1)
    monkeypatch.setattr("app.integrations.retrieval_providers.settings.LOCAL_AI_INDEX_MAX_CANDIDATES", 10)
    monkeypatch.setattr("app.integrations.retrieval_providers.settings.LOCAL_AI_MIN_SIMILARITY", 0.5)

    results = await index.search("relevant", "dept_ops", 5)

    assert loader.call_count == 3
    assert [result["chunk_id"] for result in results] == ["second"]


@pytest.mark.asyncio
async def test_index_filters_cross_department_and_non_published_after_ranking(monkeypatch):
    provider = MagicMock()
    provider.embed = AsyncMock(side_effect=[[[1, 0], [1, 0], [1, 0]], [[1, 0]]])
    provider.cosine_similarity = OllamaLocalAIProvider.cosine_similarity
    index = LocalSemanticIndex(provider)
    monkeypatch.setattr(
        CandidateRepository,
        "load_page",
        MagicMock(
            side_effect=[
                [
                    {"chunk_id": "ok", "content": "ok", "department_id": "dept_ops", "status": "published"},
                    {"chunk_id": "cross", "content": "cross", "department_id": "dept_hr", "status": "published"},
                    {"chunk_id": "draft", "content": "draft", "department_id": "dept_ops", "status": "draft"},
                ],
                [],
            ]
        ),
    )

    results = await index.search("query", "dept_ops", 10)

    assert [result["chunk_id"] for result in results] == ["ok"]


@pytest.mark.asyncio
async def test_strong_sql_result_skips_semantic_retrieval(monkeypatch):
    semantic = AsyncMock(side_effect=ConnectionError("offline"))
    monkeypatch.setattr(AIGateway.semantic_index, "search", semantic)
    monkeypatch.setattr(AIGateway.semantic_index, "fuzzy_search_cached", MagicMock(return_value=[]))
    monkeypatch.setattr(
        AIGateway.sql_provider,
        "search",
        AsyncMock(return_value=[{"chunk_id": "sql", "score": 0.9}]),
    )

    result = await AIGateway.search("query", "dept_ops", 5)

    assert result == [{"chunk_id": "sql", "score": 0.9}]
    semantic.assert_not_awaited()


@pytest.mark.asyncio
async def test_weak_sql_result_can_use_semantic_retrieval(monkeypatch):
    monkeypatch.setattr(AIGateway.semantic_index, "fuzzy_search_cached", MagicMock(return_value=[]))
    monkeypatch.setattr(AIGateway.semantic_index, "fuzzy_search", AsyncMock(return_value=[]))
    monkeypatch.setattr(
        AIGateway.sql_provider,
        "search",
        AsyncMock(return_value=[{"chunk_id": "sql", "score": 0.25}]),
    )
    monkeypatch.setattr(
        AIGateway.semantic_index,
        "search",
        AsyncMock(return_value=[{"chunk_id": "semantic", "score": 0.86}]),
    )

    result = await AIGateway.search("query", "dept_ops", 5)

    assert result == [{"chunk_id": "semantic", "score": 0.86}]


@pytest.mark.asyncio
async def test_strong_typo_match_skips_slow_semantic_retrieval(monkeypatch):
    semantic = AsyncMock(side_effect=AssertionError("semantic path should not run"))
    monkeypatch.setattr(AIGateway.semantic_index, "fuzzy_search_cached", MagicMock(return_value=[]))
    monkeypatch.setattr(
        AIGateway.sql_provider,
        "search",
        AsyncMock(return_value=[{"chunk_id": "sql", "score": 0.25}]),
    )
    monkeypatch.setattr(
        AIGateway.semantic_index,
        "fuzzy_search",
        AsyncMock(return_value=[{"chunk_id": "fuzzy", "score": 0.91}]),
    )
    monkeypatch.setattr(AIGateway.semantic_index, "search", semantic)

    result = await AIGateway.search("inboud traler seel", "dept_ops", 5)

    assert result == [{"chunk_id": "fuzzy", "score": 0.91}]
    semantic.assert_not_awaited()


def test_index_invalidation_removes_only_published_department_cache():
    index = LocalSemanticIndex(MagicMock())
    key_ops = ("dept_ops", ("published",), "nomic-embed-text")
    key_hr = ("dept_hr", ("published",), "nomic-embed-text")
    index._entries[key_ops] = MagicMock()
    index._entries[key_hr] = MagicMock()
    index._candidate_entries[key_ops] = []
    index._candidate_entries[key_hr] = []

    index.invalidate_department("dept_ops")

    assert key_ops not in index._entries
    assert key_hr in index._entries
    assert key_ops not in index._candidate_entries
    assert key_hr in index._candidate_entries


def test_public_managed_ai_url_is_rejected(monkeypatch):
    monkeypatch.setattr(
        "app.integrations.local_ai_provider.settings.LOCAL_AI_BASE_URL",
        "https://managed-ai.example.com",
    )

    with pytest.raises(ValueError, match="local or private"):
        OllamaLocalAIProvider._url("/api/chat")


def test_candidate_query_scopes_department_and_status_before_rows_are_returned(monkeypatch):
    cursor = MagicMock()
    cursor.fetchall.return_value = []
    cursor.description = []
    connection = MagicMock()
    connection.cursor.return_value.__enter__.return_value = cursor
    context = MagicMock()
    context.__enter__.return_value = connection
    monkeypatch.setattr(
        "app.integrations.retrieval_providers.get_snowflake_connection",
        MagicMock(return_value=context),
    )

    CandidateRepository.load_page("dept_ops", ("published",), 100, 0)

    sql, params = cursor.execute.call_args.args
    assert "wv.id AS workflow_version_id" in sql
    assert "LOWER(wv.status) IN (%s)" in sql
    assert "sm.department_id = %s" in sql
    assert "w.department_id = %s" in sql
    assert "MAX(candidate_version.version_number)" in sql
    assert params == ["published", "dept_ops", "dept_ops", "published", 100, 0]


@pytest.mark.asyncio
async def test_sql_fallback_returns_workflow_version_identity(monkeypatch):
    cursor = MagicMock()
    cursor.fetchall.return_value = []
    cursor.description = []
    connection = MagicMock()
    connection.cursor.return_value.__enter__.return_value = cursor
    context = MagicMock()
    context.__enter__.return_value = connection
    monkeypatch.setattr(
        "app.integrations.retrieval_providers.get_snowflake_connection",
        MagicMock(return_value=context),
    )

    await SqlLexicalRetrievalProvider().search("receive seal", "dept_ops", 5)

    sql, params = cursor.execute.call_args.args
    assert "wv.id AS workflow_version_id" in sql
    assert "w.department_id = %s" in sql
    assert "MAX(candidate_version.version_number)" in sql
    assert params[2:6] == ["published", "dept_ops", "dept_ops", "published"]


@pytest.mark.asyncio
async def test_sql_fallback_does_not_dilute_multiple_matches_in_long_question(monkeypatch):
    cursor = MagicMock()
    cursor.fetchall.return_value = []
    cursor.description = []
    connection = MagicMock()
    connection.cursor.return_value.__enter__.return_value = cursor
    context = MagicMock()
    context.__enter__.return_value = connection
    monkeypatch.setattr(
        "app.integrations.retrieval_providers.get_snowflake_connection",
        MagicMock(return_value=context),
    )

    await SqlLexicalRetrievalProvider().search(
        "inbound trailer arrives verify seal procedure", "dept_ops", 5
    )

    sql, _params = cursor.execute.call_args.args
    assert "LEAST(1.0" in sql
    assert "/ 4.0" in sql


def test_gateway_can_invalidate_all_department_indexes(monkeypatch):
    clear = MagicMock()
    monkeypatch.setattr(AIGateway.semantic_index, "clear", clear)

    AIGateway.invalidate_all()

    clear.assert_called_once_with()


@pytest.mark.asyncio
async def test_generation_unavailable_uses_extractive_fallback(monkeypatch):
    monkeypatch.setattr(
        AIGateway.local_provider,
        "generate_grounded",
        AsyncMock(side_effect=ConnectionError("offline")),
    )
    source = {
        "chunk_id": "c1",
        "document_id": "d1",
        "document_title": "SOP",
        "version_number": 1,
        "step_number": 2,
        "content": "Inspect the seal.",
    }

    result = await AIGateway.generate_response(
        {"query": "What should I inspect?", "retrieved_chunks": [source]}
    )

    assert isinstance(result, GeneratedAnswer)
    assert result.provider == "extractive"
    assert result.source_ids == ["c1"]
