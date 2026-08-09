"""Tests for free/self-hosted local AI integration and safe fallbacks."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.integrations.cortex_client import CortexClient
from app.integrations.local_ai_client import LocalAIClient


@pytest.mark.asyncio
async def test_ollama_embed_batch(monkeypatch):
    request = AsyncMock(return_value={"embeddings": [[1, 0], [0, 1]]})
    monkeypatch.setattr(LocalAIClient, "_request_json", request)

    embeddings = await LocalAIClient.embed(["one", "two"])

    assert embeddings == [[1.0, 0.0], [0.0, 1.0]]
    assert request.await_args.args[:2] == ("POST", "/api/embed")


@pytest.mark.asyncio
async def test_ollama_grounded_chat(monkeypatch):
    request = AsyncMock(return_value={"message": {"content": "Follow the verified step."}})
    monkeypatch.setattr(LocalAIClient, "_request_json", request)

    answer = await LocalAIClient.generate("VERIFIED SOURCES: step one")

    assert answer == "Follow the verified step."
    payload = request.await_args.kwargs["json"]
    assert payload["stream"] is False
    assert payload["options"]["temperature"] == 0


def test_cosine_similarity_has_no_external_numeric_dependency():
    assert LocalAIClient.cosine_similarity([1, 0], [1, 0]) == 1.0
    assert LocalAIClient.cosine_similarity([1, 0], [0, 1]) == 0.0
    assert LocalAIClient.cosine_similarity([], []) == 0.0


@pytest.mark.asyncio
async def test_local_semantic_search_ranks_only_authorized_candidates(monkeypatch):
    candidates = [
        {"chunk_id": "a", "department_id": "dept_ops", "status": "published", "content": "alpha"},
        {"chunk_id": "b", "department_id": "dept_ops", "status": "published", "content": "beta"},
    ]
    monkeypatch.setattr(CortexClient, "_load_semantic_candidates", MagicMock(return_value=candidates))
    monkeypatch.setattr(
        LocalAIClient,
        "embed",
        AsyncMock(return_value=[[1, 0], [0.9, 0.1], [0, 1]]),
    )
    monkeypatch.setattr("app.integrations.cortex_client.settings.LOCAL_AI_MIN_SIMILARITY", 0.5)

    results = await CortexClient._search_local_embeddings("alpha question", "dept_ops", 5)

    assert [item["chunk_id"] for item in results] == ["a"]


@pytest.mark.asyncio
async def test_generation_falls_back_to_extract_when_ollama_is_down(monkeypatch):
    monkeypatch.setattr("app.integrations.cortex_client.settings.LOCAL_AI_ENABLED", True)
    monkeypatch.setattr("app.integrations.cortex_client.settings.CORTEX_COMPLETE_ENABLED", False)
    monkeypatch.setattr(LocalAIClient, "generate", AsyncMock(side_effect=ConnectionError("offline")))

    answer = await CortexClient.generate_response(
        {
            "query": "What is the step?",
            "retrieved_chunks": [
                {
                    "document_title": "Receiving SOP",
                    "version_number": 2,
                    "content": "Inspect the seal.",
                }
            ],
        }
    )

    assert answer == "According to 'Receiving SOP' (v2), Inspect the seal."
