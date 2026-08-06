"""Unit tests for FastAPI entry point and health check endpoint."""

from unittest.mock import patch
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
