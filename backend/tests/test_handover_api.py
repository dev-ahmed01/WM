"""Phase B/C: authorization, bounded exception capture and atomic review endpoints."""
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.core.security import create_access_token
from app.main import app

client = TestClient(app)


def identity(role="employee", dept="warehouse", user="worker"):
    return {"Authorization": "Bearer " + create_access_token(user, role, dept)}


PAYLOAD = {
    "conversation_id": "conv_existing",
    "recipient_label": "Night shift warehouse lead",
    "disposition": "blocked_supervisor",
    "exception_type": "damage",
    "severity": "high",
    "next_action": "Inspect the carton with the shift supervisor.",
    "notes": "Awaiting a decision.",
}


def test_handover_submit_requires_owner_context_and_disallows_scope_spoofing():
    assert client.post("/api/v1/handover", json=PAYLOAD).status_code == 401
    with patch("app.api.v1.handover.HandoverRepository.submit", return_value={"id": "hov_1"}) as save:
        response = client.post("/api/v1/handover", headers=identity(), json=PAYLOAD)
    assert response.status_code == 201, response.text
    assert save.call_args.args[:3] == ("warehouse", "worker", "conv_existing")
    assert client.post(
        "/api/v1/handover", headers=identity(), json={**PAYLOAD, "department_id": "finance"},
    ).status_code == 422
    with patch("app.api.v1.handover.HandoverRepository.submit", return_value=None):
        hidden = client.post("/api/v1/handover", headers=identity(), json=PAYLOAD)
    assert hidden.status_code == 404


def test_exception_guardrails_are_enforced_before_db():
    headers = identity()
    bad = [
        {**PAYLOAD, "severity": "critical", "exception_type": "none"},
        {**PAYLOAD, "disposition": "information", "exception_type": "safety_concern"},
        {**PAYLOAD, "next_action": "x"},
        {**PAYLOAD, "severity": "unknown"},
        {**PAYLOAD, "notes": "a" * 1501},
    ]
    for request in bad:
        assert client.post("/api/v1/handover", headers=headers, json=request).status_code == 422


def test_worker_list_is_own_only_and_manager_reviews_department(monkeypatch):
    with patch("app.api.v1.handover.HandoverRepository.list", return_value=[]) as listing:
        employee = client.get("/api/v1/handover", headers=identity())
        assert employee.status_code == 200
        assert listing.call_args.args == ("warehouse", "worker", False, 40)
    with patch("app.api.v1.handover.HandoverRepository.list", return_value=[]) as listing:
        manager = client.get("/api/v1/handover?limit=12&department_id=finance", headers=identity("manager"))
        assert manager.status_code == 200
        assert listing.call_args.args == ("warehouse", "worker", True, 12)
    assert client.get("/api/v1/handover?limit=900", headers=identity()).status_code == 422


def test_reviewer_ownership_requires_manager_and_is_single_claim():
    assert client.post("/api/v1/handover/hov_1/claim", headers=identity()).status_code == 403
    with patch("app.api.v1.handover.HandoverRepository.claim",
               return_value={"id":"hov_1", "assigned_to_user_id":"boss"}) as claimed:
        accepted = client.post("/api/v1/handover/hov_1/claim",
                               headers=identity("manager",user="boss"))
    assert accepted.status_code == 200
    assert claimed.call_args.args == ("warehouse","boss","hov_1")
    with patch("app.api.v1.handover.HandoverRepository.claim",return_value=None):
        repeated = client.post("/api/v1/handover/hov_1/claim",headers=identity("manager"))
    assert repeated.status_code == 409


def test_manager_review_never_available_to_worker_or_forged_user():
    review = {"decision": "follow_up_requested", "review_note": "Please isolate goods for manual verification."}
    assert client.post("/api/v1/handover/hov_1/review", headers=identity(), json=review).status_code == 403
    with patch("app.api.v1.handover.HandoverRepository.review", return_value={"id":"hov_1"}) as store:
        result = client.post("/api/v1/handover/hov_1/review", headers=identity("manager",user="boss"), json=review)
    assert result.status_code == 200
    assert store.call_args.args == ("warehouse", "boss", "hov_1", "follow_up_requested", review["review_note"])
    assert client.post("/api/v1/handover/hov_1/review", headers=identity("manager"),
                       json={**review, "review_note": ""}).status_code == 422
    with patch("app.api.v1.handover.HandoverRepository.review", return_value=None):
        assert client.post("/api/v1/handover/hov_1/review", headers=identity("manager"), json=review).status_code == 409


def test_store_failure_never_leaks_connection_string():
    with patch("app.api.v1.handover.HandoverRepository.submit",
               side_effect=RuntimeError("postgresql://secret-password@private-host")):
        result = client.post("/api/v1/handover", headers=identity(), json=PAYLOAD)
    assert result.status_code == 503
    assert "private-host" not in result.text
