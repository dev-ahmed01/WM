"""Unit tests for GET /api/v1/copilot/history endpoint."""

import pytest
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.copilot import router as copilot_router
from app.core.security import create_access_token

app = FastAPI()
app.include_router(copilot_router, prefix="/api/v1")

client = TestClient(app)

EMP_TOKEN = create_access_token(user_id="usr_emp001", role="employee", department_id="dept_eng")


@patch("app.repositories.conversation_repository.ConversationRepository.list_user_conversations")
@patch("app.repositories.conversation_repository.ConversationRepository.count_user_conversations")
def test_get_copilot_history_success(mock_count, mock_list):
    mock_list.return_value = [
        {
            "id": "conv_12345",
            "title": "Equipment Calibration SOP",
            "status": "completed",
            "started_at": "2026-08-04T00:00:00",
            "last_message_preview": "Calibration procedure step 2 confirmed.",
        }
    ]
    mock_count.return_value = 1

    headers = {"Authorization": f"Bearer {EMP_TOKEN}"}
    response = client.get("/api/v1/copilot/history", headers=headers)

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert len(data["sessions"]) == 1
    assert data["sessions"][0]["id"] == "conv_12345"
    assert data["sessions"][0]["title"] == "Equipment Calibration SOP"
    assert data["sessions"][0]["status"] == "completed"
    assert data["sessions"][0]["last_message_preview"] == "Calibration procedure step 2 confirmed."


def test_get_copilot_history_unauthorized():
    response = client.get("/api/v1/copilot/history")
    assert response.status_code == 401
