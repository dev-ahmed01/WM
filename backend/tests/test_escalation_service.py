"""Tests for the authenticated backend-to-n8n escalation contract."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.escalation import EscalationService


@pytest.mark.asyncio
@patch("app.services.escalation.httpx.AsyncClient")
async def test_escalation_webhook_sends_internal_secret(mock_async_client, monkeypatch):
    monkeypatch.setattr("app.services.escalation.settings.N8N_NOTIFICATIONS_ENABLED", True)
    repository = MagicMock()
    repository.create.return_value = "esc_1"
    repository.update_status.return_value = True
    http_client = AsyncMock()
    http_client.post.return_value.status_code = 202
    mock_async_client.return_value.__aenter__.return_value = http_client

    escalation_id = await EscalationService(repository).escalate("msg_1", "Needs supervisor")

    assert escalation_id == "esc_1"
    _, kwargs = http_client.post.await_args
    assert kwargs["headers"]["X-WorkMate-Webhook-Secret"]
    assert kwargs["json"]["conversation_message_id"] == "msg_1"
    repository.update_status.assert_called_once()


@pytest.mark.asyncio
@patch("app.services.escalation.httpx.AsyncClient")
async def test_escalation_skips_webhook_when_notifications_are_disabled(mock_async_client):
    repository = MagicMock()
    repository.create.return_value = "esc_1"

    escalation_id = await EscalationService(repository).escalate("msg_1", "Needs supervisor")

    assert escalation_id == "esc_1"
    mock_async_client.assert_not_called()
