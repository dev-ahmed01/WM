"""Focused tests for real Copilot retrieval and Cortex generation paths."""

import json
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest

from app.integrations.cortex_client import CortexClient


def _connection_with_cursor(cursor):
    @contextmanager
    def factory():
        connection = MagicMock()
        connection.cursor.return_value.__enter__.return_value = cursor
        yield connection

    return factory


@pytest.mark.asyncio
async def test_search_preview_enforces_department_and_status_filters(monkeypatch):
    cursor = MagicMock()
    cursor.fetchone.return_value = (
        json.dumps(
            {
                "results": [
                    {
                        "chunk_id": "chunk-1",
                        "document_id": "doc-1",
                        "document_title": "Receiving SOP",
                        "version_number": 1,
                        "state_id": "state-1",
                        "step_number": 1,
                        "step_title": "Inspect seal",
                        "search_content": "Inspect the seal before unloading.",
                        "department_id": "dept_inbound",
                        "status": "published",
                    }
                ]
            }
        ),
    )
    monkeypatch.setattr("app.integrations.cortex_client.get_snowflake_connection", _connection_with_cursor(cursor))

    results = await CortexClient.search("broken shipment seal", "dept_inbound", limit=3)

    assert results[0]["content"] == "Inspect the seal before unloading."
    sql = cursor.execute.call_args.args[0]
    assert '"department_id":"dept_inbound"' in sql
    assert '"status":"published"' in sql


@pytest.mark.asyncio
async def test_generate_response_calls_ai_complete(monkeypatch):
    cursor = MagicMock()
    cursor.fetchone.return_value = ("Stop unloading and notify the inbound supervisor.",)
    monkeypatch.setattr("app.integrations.cortex_client.get_snowflake_connection", _connection_with_cursor(cursor))

    answer = await CortexClient.generate_response(
        {
            "query": "What if the seal is broken?",
            "retrieved_chunks": [
                {
                    "document_title": "Receiving SOP",
                    "version_number": 1,
                    "step_number": 1,
                    "content": "Stop unloading and notify the inbound supervisor.",
                }
            ],
        }
    )

    assert answer == "Stop unloading and notify the inbound supervisor."
    assert cursor.execute.call_args.args[0] == "SELECT AI_COMPLETE(%s, %s)"


@pytest.mark.asyncio
async def test_no_arbitrary_department_fallback(monkeypatch):
    monkeypatch.setattr("app.integrations.cortex_client.settings.CORTEX_SEARCH_ENABLED", False)
    cursor = MagicMock()
    cursor.fetchall.return_value = []
    cursor.description = []
    monkeypatch.setattr("app.integrations.cortex_client.get_snowflake_connection", _connection_with_cursor(cursor))

    results = await CortexClient.search("broken shipment seal", "dept_inbound")

    assert results == []
    executed_sql = cursor.execute.call_args.args[0]
    assert "AND (" in executed_sql
    assert "ORDER BY score DESC" in executed_sql
