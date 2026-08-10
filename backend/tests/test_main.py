"""Unit tests for FastAPI entry point and health check endpoint."""

from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


@patch("app.main.ping_snowflake_connection")
def test_health_check_connected(mock_ping):
    mock_ping.return_value = True
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["database"] == "connected"
    assert "version" in data


@patch("app.main.ping_snowflake_connection")
def test_health_check_unreachable_graceful(mock_ping):
    mock_ping.return_value = False
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "degraded"
    assert data["database"] == "unreachable"


@patch("app.main.AIGateway.health", new_callable=AsyncMock)
def test_ai_health_reports_local_provider(mock_health):
    mock_health.return_value = {"enabled": True, "reachable": True, "required_models": ["qwen2.5:3b", "nomic-embed-text"], "installed_models": ["qwen2.5:3b", "nomic-embed-text"], "missing_models": [], "chat_ready": True, "embedding_ready": True}

    response = client.get("/health/ai")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["provider"] == "ollama"


@patch("app.main.AIGateway.health", new_callable=AsyncMock)
def test_ai_health_is_degraded_when_required_model_is_missing(mock_health):
    mock_health.return_value = {
        "enabled": True,
        "reachable": True,
        "required_models": ["qwen2.5:3b", "nomic-embed-text"],
        "installed_models": ["qwen2.5:3b"],
        "missing_models": ["nomic-embed-text"],
        "chat_ready": True,
        "embedding_ready": False,
    }

    response = client.get("/health/ai")

    assert response.status_code == 200
    assert response.json()["status"] == "degraded"
    assert response.json()["local"]["missing_models"] == ["nomic-embed-text"]
