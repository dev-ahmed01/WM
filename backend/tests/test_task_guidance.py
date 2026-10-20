"""Phase 5A: task-context answers remain scoped, cited, read-only and fail closed."""
import pytest
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient
from app.core.security import create_access_token
from app.main import app
from app.repositories.work_execution_repository import ExecutionNotFound
from app.services.task_guidance import TaskGuidanceService

client=TestClient(app)

def auth(role="employee",dept="warehouse",actor="operator"):
    return {"Authorization":"Bearer "+create_access_token(actor,role,dept)}

def position(status="active"):
    return {
        "work_id":"wrk_1","status":status,"workflow_version_id":"v_published",
        "session_id":"sess_1","case_id":"case_1" if status=="blocked" else None,
        "step":{"id":"step_1","instruction":"Inspect receiving seals for physical damage.",
                "expected_output_type":"TEXT_INPUT",
                "evidence_specs":[{"evidence_type":"PHOTO_JPEG","is_required":True}]},
        "state":{"id":"state_1","title":"Receiving seal","state_type":"ATOMIC_STEP"},
        "decision_options":[],"decision_question":None,
        "safety_gates":[],"completed_steps":0,"total_steps":2,
    }


@pytest.mark.asyncio
async def test_uses_real_published_state_and_required_evidence():
    state=position()
    result=await TaskGuidanceService.answer(state,"warehouse","current_step")
    assert "Inspect receiving seals" in result["answer"]
    assert result["citations"][0]["workflow_version_id"]=="v_published"
    assert result["citations"][0]["step_id"]=="step_1"
    assert result["read_only"]
    proof=await TaskGuidanceService.answer(state,"warehouse","evidence")
    assert "JPEG photograph" in proof["answer"]
    assert "not independently verified" in proof["answer"]
    assert proof["citations"][0]["step_id"]=="step_1"


@pytest.mark.asyncio
async def test_blocked_work_fails_closed_without_reference_search():
    with patch("app.services.task_guidance.ReferenceAnswerService.answer",
               new_callable=AsyncMock) as ref:
        result=await TaskGuidanceService.answer(
            position("blocked"),"warehouse","ask","Can I bypass the hold?"
        )
    assert result["requires_supervisor"] and "blocked" in result["answer"]
    assert "case_1" in result["answer"]
    assert result["read_only"]
    ref.assert_not_called()


@pytest.mark.asyncio
async def test_reference_only_succeeds_with_verified_citation():
    from types import SimpleNamespace
    verified=SimpleNamespace(is_grounded=True,citations=[
        SimpleNamespace(document_id="doc_1",document_title="Inbound seal policy",
                        chunk_id="chunk_1",excerpt="Isolate damaged incoming cartons.")
    ],answer="From an approved reference: Isolate damaged incoming cartons.")
    with patch("app.services.task_guidance.ReferenceAnswerService.answer",
               new_callable=AsyncMock,return_value=verified) as ref:
        result=await TaskGuidanceService.answer(position(),"warehouse",
                                                "ask","What about damaged cartons?")
    assert result["reference_grounded"] and result["read_only"]
    assert result["citations"][0]["source_type"]=="approved_reference"
    ref.assert_awaited_once_with("What about damaged cartons?","warehouse")


@pytest.mark.asyncio
async def test_unverified_or_failed_reference_cannot_create_instructions():
    fake=type("Failed",(),{"is_grounded":False,"citations":[]})()
    for response in (fake,None):
        with patch("app.services.task_guidance.ReferenceAnswerService.answer",
                   new_callable=AsyncMock,return_value=response):
            result=await TaskGuidanceService.answer(
                position(),"warehouse","ask","Show unverified instructions"
            )
        assert result["reference_grounded"] is False
        assert result["requires_supervisor"] is True
        assert result["citations"][0]["source_type"]=="published_sop"
        assert "could not find an approved reference" in result["answer"]


def test_guidance_api_scopes_worker_and_rejects_invalid_payloads():
    endpoint="/api/v1/work/guidance/wrk_1"
    assert client.post(endpoint,json={"intent":"current_step"}).status_code==401
    assert client.post(endpoint,headers=auth(),json={"intent":"ask","question":"a"}).status_code==422
    assert client.post(endpoint,headers=auth(),json={"intent":"skip","question":"skip work"}).status_code==422
    assert client.post(endpoint,headers=auth(),json={"intent":"current_step","department_id":"another"}).status_code==422
    with patch("app.api.v1.task_guidance.WorkExecutionRepository.position",
               side_effect=ExecutionNotFound()):
        result=client.post(endpoint,headers=auth(),json={"intent":"current_step"})
    assert result.status_code==404


def test_api_uses_authenticated_actor_department_and_never_executes_steps():
    endpoint="/api/v1/work/guidance/wrk_1"
    with patch("app.api.v1.task_guidance.WorkExecutionRepository.position",
               return_value=position()) as get_position:
        result=client.post(endpoint,headers=auth(),json={"intent":"evidence"})
    assert result.status_code==200,result.text
    assert get_position.call_args.args==("warehouse","operator",False,"wrk_1")
    assert result.json()["read_only"] is True
    assert "JPEG photograph" in result.json()["answer"]
