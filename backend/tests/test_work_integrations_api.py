"""Phase 6A route acceptance: no external caller can authoritatively create tasks."""
from unittest.mock import patch
from fastapi.testclient import TestClient

from app.core.security import create_access_token
from app.main import app
from app.repositories.work_integration_intake_repository import (
    IntegrationConflict,IntegrationNotFound,
)

client=TestClient(app)


def auth(role="manager",department="dock",actor="reviewer"):
    return {"Authorization":"Bearer "+create_access_token(actor,role,department)}


ITEM={
    "source_system":"custom_wms",
    "external_event_id":"shipment.received.4001",
    "external_work_id":"SHIP-4001",
    "title":"Verify inbound shipment 4001",
    "work_type":"receiving",
    "priority":"high",
    "instructions":"Inspect carton count and hold damaged goods.",
    "assigned_to":None,
}


def test_integrations_require_manager_and_reject_forged_safety_controls():
    url="/api/v1/work/integrations/intake"
    assert client.post(url,json=ITEM).status_code==401
    assert client.post(url,headers=auth("employee"),json=ITEM).status_code==403
    assert client.get(url,headers=auth("employee")).status_code==403
    for injected in (
        {"department_id":"other"},{"status":"completed"},{"workflow_version_id":"sop1"},
        {"auto_execute":True},{"release_hold":True},{"source_system":"unlisted"},
        {"external_event_id":"bad event space"},{"assigned_to":""},
        {"title":"x"},{"work_type":"start_machine"},
    ):
        assert client.post(url,headers=auth(),json={**ITEM,**injected}).status_code==422
    with patch("app.api.v1.work_integrations.IntegrationIntakeRepository.stage",
               return_value={"status":"pending","id":"int_1","replayed":False}) as staged:
        result=client.post(url,headers=auth("manager","dock","operator1"),json=ITEM)
    assert result.status_code==201
    assert staged.call_args.args[:2]==("dock","operator1")
    assert staged.call_args.args[2]["assigned_to"] is None


def test_staging_replay_contract_and_list_roles():
    url="/api/v1/work/integrations/intake"
    with patch("app.api.v1.work_integrations.IntegrationIntakeRepository.stage",
               return_value={"id":"int_1","status":"accepted","replayed":True}) as stage:
        retry=client.post(url,headers=auth(),json=ITEM)
    assert retry.status_code==201 and retry.json()["replayed"] is True
    with patch("app.api.v1.work_integrations.IntegrationIntakeRepository.list",
               return_value=[{"id":"int_1","status":"pending"}]) as listing:
        items=client.get(url+"?limit=2",headers=auth())
    assert items.status_code==200 and len(items.json()["items"])==1
    assert listing.call_args.args==("dock","reviewer",2)


def test_independent_import_acceptance_and_error_redaction():
    url="/api/v1/work/integrations/intake/int_1/decision"
    body={"decision":"accepted","decision_note":"Validated the inbound order and assigned it for SOP planning."}
    assert client.post(url,headers=auth("employee"),json=body).status_code==403
    for injected in (
        {"release_original":True},{"auto_bind_sop":True},{"status":"completed"},
        {"decision":"executed"},{"decision_note":"short"},
    ):
        assert client.post(url,headers=auth(),json={**body,**injected}).status_code==422
    with patch("app.api.v1.work_integrations.IntegrationIntakeRepository.decide",
               return_value={"status":"accepted","work_item_id":"wrk_x"}) as decide:
        response=client.post(url,headers=auth("manager","dock","approver"),json=body)
    assert response.status_code==200
    assert decide.call_args.args==("dock","approver","int_1","accepted",body["decision_note"])
    with patch("app.api.v1.work_integrations.IntegrationIntakeRepository.decide",
               side_effect=IntegrationConflict("Already imported.")):
        assert client.post(url,headers=auth(),json=body).status_code==409
    with patch("app.api.v1.work_integrations.IntegrationIntakeRepository.decide",
               side_effect=IntegrationNotFound()):
        assert client.post(url,headers=auth(),json=body).status_code==404
    with patch("app.api.v1.work_integrations.IntegrationIntakeRepository.decide",
               side_effect=RuntimeError("postgresql://secret:pass@dbserver")):
        failure=client.post(url,headers=auth(),json=body)
    assert failure.status_code==503 and "dbserver" not in failure.text
