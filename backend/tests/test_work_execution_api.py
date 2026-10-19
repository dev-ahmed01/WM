"""Phase 2 API: authorization, strict evidence boundaries and fail-closed responses."""
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.core.security import create_access_token
from app.main import app

client=TestClient(app)


def auth(role="employee",dept="receiving",actor="worker"):
    return {"Authorization":"Bearer "+create_access_token(actor,role,dept)}


def test_published_procedures_and_binding_are_manager_only():
    assert client.get("/api/v1/work/execution/procedures",headers=auth()).status_code==403
    with patch("app.api.v1.work_execution.WorkExecutionRepository.procedures",
               return_value=[{"workflow_version_id":"pub_1"}]) as source:
        r=client.get("/api/v1/work/execution/procedures",headers=auth("manager"))
    assert r.status_code==200 and source.call_args.args==("receiving",)
    assert client.post("/api/v1/work/execution/wrk_1/bind",headers=auth(),
                       json={"workflow_version_id":"pub_1"}).status_code==403
    with patch("app.api.v1.work_execution.WorkExecutionRepository.bind",
               return_value={"status":"ready","work_id":"wrk_1"}) as binder:
        r=client.post("/api/v1/work/execution/wrk_1/bind",headers=auth("manager"),
                      json={"workflow_version_id":"pub_1"})
    assert r.status_code==200 and binder.call_args.args==("receiving","worker","wrk_1","pub_1")
    assert client.post("/api/v1/work/execution/wrk_1/bind",headers=auth("manager"),
                       json={"workflow_version_id":"pub_1","status":"completed"}).status_code==422


def test_worker_cannot_spoof_department_status_or_step_transition():
    with patch("app.api.v1.work_execution.WorkExecutionRepository.start",
               return_value={"status":"active","work_id":"wrk_1"}) as starter:
        assert client.post("/api/v1/work/execution/wrk_1/start",headers=auth()).status_code==200
    assert starter.call_args.args==("receiving","worker","wrk_1")
    proof={"step_id":"s1","confirmation":True}
    for spoof in ({"department_id":"foreign"},{"status":"completed"},
                  {"rule_results":{"SAFETY":True}},{"state_id":"end"}):
        assert client.post("/api/v1/work/execution/wrk_1/step",headers=auth(),
                           json={**proof,**spoof}).status_code==422
    assert client.post("/api/v1/work/execution/wrk_1/step",headers=auth(),
                       json={**proof,"number":float("inf")}).status_code==422


def test_explicit_observation_is_forwarded_only_to_safeguarded_repository():
    proof={"step_id":"state_step","confirmation":True,"text":"Seal checked",
           "evidence_files":[]}
    with patch("app.api.v1.work_execution.WorkExecutionRepository.progress",
               return_value={"status":"active","completed_steps":1}) as writer:
        r=client.post("/api/v1/work/execution/wrk_1/step",headers=auth(),json=proof)
    assert r.status_code==200
    assert writer.call_args.args==("receiving","worker","wrk_1","state_step",
                                   True,"Seal checked",None,[])
    with patch("app.api.v1.work_execution.WorkExecutionRepository.decide",
               return_value={"status":"completed"}) as chooser:
        r=client.post("/api/v1/work/execution/wrk_1/decision",headers=auth(),
                      json={"decision_option":"APPROVE"})
    assert r.status_code==200
    assert chooser.call_args.args==("receiving","worker","wrk_1","APPROVE")


def test_missing_invalid_cross_department_and_store_errors_are_masked():
    from app.repositories.work_execution_repository import ExecutionConflict,ExecutionNotFound
    with patch("app.api.v1.work_execution.WorkExecutionRepository.position",
               side_effect=ExecutionNotFound()):
        r=client.get("/api/v1/work/execution/wrk_1",headers=auth())
    assert r.status_code==404
    with patch("app.api.v1.work_execution.WorkExecutionRepository.progress",
               side_effect=ExecutionConflict("Mandatory JPEG evidence missing")):
        r=client.post("/api/v1/work/execution/wrk_1/step",headers=auth(),
                      json={"step_id":"s1","confirmation":True})
    assert r.status_code==409 and "Mandatory JPEG" in r.text
    with patch("app.api.v1.work_execution.WorkExecutionRepository.start",
               side_effect=RuntimeError("postgresql://hidden@private-host")):
        r=client.post("/api/v1/work/execution/wrk_1/start",headers=auth())
    assert r.status_code==503 and "private-host" not in r.text


def test_pause_block_requires_reason_and_timeline_is_scoped():
    assert client.post("/api/v1/work/execution/wrk_1/block",headers=auth(),
                       json={"reason":"short"}).status_code==422
    with patch("app.api.v1.work_execution.WorkExecutionRepository.change_status",
               return_value={"status":"blocked"}) as block:
        r=client.post("/api/v1/work/execution/wrk_1/block",headers=auth(),
                      json={"reason":"Seal broken, supervisor inspection required."})
    assert r.status_code==200
    assert block.call_args.args[0:4]==("receiving","worker","wrk_1","block")
    with patch("app.api.v1.work_execution.WorkExecutionRepository.timeline",
               return_value=[]) as events:
        r=client.get("/api/v1/work/execution/wrk_1/timeline",headers=auth("manager"))
    assert r.status_code==200
    assert events.call_args.args==("receiving","worker",True,"wrk_1")
