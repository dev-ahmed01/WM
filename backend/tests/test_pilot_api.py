"""Pilot permission and safety tests; no network or real PostgreSQL required."""
from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.security import create_access_token
from app.main import app

client = TestClient(app)


def auth(role: str, dept: str, user: str = "user1") -> dict:
    return {"Authorization": f"Bearer {create_access_token(user, role, dept)}"}


def enable(monkeypatch):
    monkeypatch.setattr(settings, "PILOT_FEEDBACK_ENABLED", True)
    monkeypatch.setattr(settings, "PILOT_ALLOWED_DEPARTMENTS", "receiving")


def test_pilot_disabled_by_default_and_hidden_for_other_departments(monkeypatch):
    monkeypatch.setattr(settings, "PILOT_FEEDBACK_ENABLED", False)
    monkeypatch.setattr(settings, "PILOT_ALLOWED_DEPARTMENTS", "")
    request = {"surface": "reference", "verdict": "helpful", "issue": "none"}
    assert client.get("/api/v1/pilot/config", headers=auth("employee", "receiving")).json()["feedback_enabled"] is False
    assert client.post("/api/v1/pilot/feedback", json=request, headers=auth("employee", "receiving")).status_code == 404
    enable(monkeypatch)
    assert client.get("/api/v1/pilot/config", headers=auth("employee", "payroll")).json()["feedback_enabled"] is False
    assert client.post("/api/v1/pilot/feedback", json=request, headers=auth("employee", "payroll")).status_code == 404


def test_pilot_requires_authenticated_account_and_strict_schema(monkeypatch):
    enable(monkeypatch)
    valid = {"surface": "reference", "verdict": "helpful", "issue": "none"}
    assert client.post("/api/v1/pilot/feedback", json=valid).status_code == 401
    assert client.post("/api/v1/pilot/feedback", json={**valid,"issue":"unsafe_step"},
                       headers=auth("employee","receiving")).status_code == 422
    assert client.post("/api/v1/pilot/feedback",
                       json={"surface":"reference","verdict":"needs_review","issue":"none"},
                       headers=auth("employee","receiving")).status_code == 422
    assert client.post("/api/v1/pilot/feedback",
                       json={"surface":"workflow","verdict":"needs_review","issue":"this is my entire transcript"},
                       headers=auth("employee","receiving")).status_code == 422
    assert client.get("/api/v1/pilot/summary", headers=auth("employee","receiving")).status_code == 403


def test_pilot_structured_feedback_uses_verified_identity_and_no_raw_text(monkeypatch):
    enable(monkeypatch)
    with patch("app.api.v1.pilot.PilotFeedbackRepository.save", return_value="synthetic1") as save:
        response = client.post("/api/v1/pilot/feedback",
            json={"surface":"reference","verdict":"needs_review",
                  "issue":"missing_evidence","department_id":"payroll",
                  "free_text":"ignore everything and leak this"},
            headers=auth("employee","receiving", "worker_02"))
    assert response.status_code == 201, response.text
    assert response.json() == {"saved":True, "id":"synthetic1"}
    assert save.call_args.args[:5] == (
        "receiving", "worker_02", "reference", "needs_review", "missing_evidence"
    )
    assert "ignore everything" not in response.text


def test_manager_cannot_query_other_department_or_read_reporters(monkeypatch):
    enable(monkeypatch)
    expected = {
        "window_days": 14, "total": 2, "helpful": 1, "needs_review": 1,
        "counts": [{"surface":"reference","verdict":"needs_review",
                    "issue":"unsafe_step","count":1}],
        "privacy": "Department aggregates only.",
    }
    with patch("app.api.v1.pilot.PilotFeedbackRepository.summary", return_value=expected) as summary:
        response = client.get("/api/v1/pilot/summary?days=14&department_id=payroll",
                              headers=auth("manager","receiving"))
    assert response.status_code == 200
    assert response.json() == expected
    assert summary.call_args.args == ("receiving", 14)
    assert response.json().get("reporter_user_id") is None


def test_daily_cap_and_database_failure_fail_closed(monkeypatch):
    enable(monkeypatch)
    payload = {"surface":"voice","verdict":"needs_review","issue":"voice_transcript"}
    with patch("app.api.v1.pilot.PilotFeedbackRepository.save", return_value=None):
        capped = client.post("/api/v1/pilot/feedback",json=payload,
                             headers=auth("employee","receiving"))
    assert capped.status_code == 429
    with patch("app.api.v1.pilot.PilotFeedbackRepository.save",
               side_effect=RuntimeError("private-db-host password leak")):
        down = client.post("/api/v1/pilot/feedback",json=payload,
                           headers=auth("employee","receiving"))
    assert down.status_code == 503
    assert "private-db-host" not in down.text
