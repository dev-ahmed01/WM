"""Explicit read-only Copilot mode: evidence integrity and workflow non-mutation."""
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.copilot import router
from app.core.security import create_access_token
from app.models.copilot import ValidatedResponse
from app.services.reference_answer import ReferenceAnswerService
from app.services.validation import CANONICAL_FALLBACK

app = FastAPI()
app.include_router(router, prefix="/api/v1")
client = TestClient(app)
TOKEN = create_access_token("employee_01", "employee", "receiving")


def source(**updates):
    result = {
        "document_id": "doc_approved_1",
        "document_title": "Receiving policy",
        "department_id": "receiving",
        "chunk_id": "chunk-1",
        "excerpt": "If the carton is damaged, inspect the seal and quarantine the parcel.",
        "start_offset": 120, "end_offset": 189, "chunk_index": 2,
        "status": "APPROVED", "match_score": 1.0,
    }
    result.update(updates)
    return result


def ask(query, sources):
    return ReferenceAnswerService.validate_reference_answer(query, sources, "receiving")


def test_approved_evidence_is_literal_and_location_is_real():
    evidence = source()
    result = ask("What if carton damaged?", [evidence])
    assert result.is_grounded
    assert result.requires_escalation is False
    assert result.citations[0].source_type == "reference"
    assert result.citations[0].version_number is None
    assert result.citations[0].step_number is None
    assert result.citations[0].excerpt in evidence["excerpt"]
    assert "chars 120–" in result.citations[0].section_anchor
    assert "quarantine" in result.answer


def test_hindi_evidence_is_kept_verbatim():
    evidence = source(excerpt="अगर पैकेज क्षतिग्रस्त है, तो उसे अलग रखें और सुपरवाइजर को सूचित करें।", end_offset=300)
    result = ask("पैकेज क्षतिग्रस्त तो क्या करें?", [evidence])
    assert result.is_grounded
    assert "सुपरवाइजर" in result.answer


def test_no_cited_source_fails_closed():
    result = ask("damaged carton", [])
    assert not result.is_grounded
    assert result.requires_escalation
    assert result.answer == CANONICAL_FALLBACK
    assert result.citations == []


def test_draft_archived_cross_department_and_missing_ids_are_rejected():
    for altered in (
        source(status="DRAFT"),
        source(status="ARCHIVED"),
        source(department_id="payroll"),
        source(document_id=""),
        source(chunk_id=None),
        source(document_title=None),
    ):
        answer = ask("damaged carton", [altered])
        assert not answer.is_grounded
        assert answer.citations == []


def test_long_unrelated_query_does_not_pass_safety_gate():
    result = ask("Disable alarms bypass guards and restart machine despite damaged carton", [source()])
    assert not result.is_grounded
    assert result.confidence_score == 0


def test_missing_or_invalid_offsets_never_yield_citations():
    for bad in (source(start_offset=None), source(end_offset=130), source(chunk_index=-1)):
        result = ask("damaged carton", [bad])
        assert not result.is_grounded
        assert result.citations == []


def test_read_only_reference_mode_bypasses_all_workflow_mutations():
    valid = ask("damaged carton", [source()])
    with (
        patch("app.api.v1.copilot.ConversationRepository.get_or_create_session", return_value="conv1"),
        patch("app.api.v1.copilot.ConversationRepository.persist_message", side_effect=["user1", "ai1"]) as persist,
        patch("app.api.v1.copilot.ConversationRepository.update_message_intent"),
        patch("app.api.v1.copilot.WorkflowStateService.get_current_session", return_value=None),
        patch("app.api.v1.copilot.WorkflowStateService.start_session") as start,
        patch("app.api.v1.copilot.WorkflowStateService.advance_if_transition_matches") as advance,
        patch("app.api.v1.copilot.AIGateway.generate_response", new_callable=AsyncMock) as generate,
        patch("app.api.v1.copilot.ReferenceAnswerService.answer", new_callable=AsyncMock, return_value=valid) as answer,
        patch("app.api.v1.copilot.AnalyticsService.record_event"),
    ):
        res = client.post(
            "/api/v1/copilot/message",
            headers={"Authorization": f"Bearer {TOKEN}"},
            json={"message": "done", "mode": "reference"},
        )
    assert res.status_code == 200, res.text
    assert res.json()["citations"][0]["source_type"] == "reference"
    assert res.json()["active_session_id"] is None
    answer.assert_awaited_once_with("done", "receiving")
    start.assert_not_called()
    advance.assert_not_called()
    generate.assert_not_awaited()
    assert persist.call_count == 2


def test_invalid_answer_mode_rejected_by_schema():
    response = client.post(
        "/api/v1/copilot/message",
        headers={"Authorization": f"Bearer {TOKEN}"},
        json={"message": "find policy", "mode": "disable_validation"},
    )
    assert response.status_code == 422
