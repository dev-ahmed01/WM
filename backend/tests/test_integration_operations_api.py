"""Phase 6D: live counts and audit API; no self-declared production readiness."""
from unittest.mock import patch
from fastapi.testclient import TestClient
from app.main import app
from app.core.security import create_access_token
from app.repositories.work_integration_operations_repository import (
    IntegrationOperationsRepository,OperationsNotFound,OperationsConflict,_source_alerts,
)
from app.core.config import settings
from app.services.work_integration_outbound import configured_target

client=TestClient(app)
def auth(role="admin",dept="receiving",actor="a_1"):
    return {"Authorization":"Bearer "+create_access_token(actor,role,dept)}

def test_ops_admin_only_strict_payload_and_dept_server_owned():
    url="/api/v1/work/integrations/operations/readiness"
    assert client.get(url).status_code==401
    assert client.get(url,headers=auth("manager")).status_code==403
    assert client.get(url,headers=auth("employee")).status_code==403
    synthetic={"decision":"NO_GO","operational_status":"needs_attention",
               "counts":{"sources":1,"dead_outbound":1,"open_alerts":1},
               "alerts":[{"code":"dead_outbound","severity":"critical","count":1,
                          "source_id":"warehouse-east"}],
               "field_verification":"not_automatically_verified"}
    with patch("app.api.v1.work_integrations.IntegrationOperationsRepository.snapshot",
               return_value=synthetic) as snapshot:
        r=client.get(url,headers=auth())
    assert r.status_code==200 and r.json()["decision"]=="NO_GO"
    assert snapshot.call_args.args==("receiving","a_1")
    endpoint="/api/v1/work/integrations/operations/actions"
    data={"source_id":"warehouse-east","issue_code":"dead_outbound",
          "action":"acknowledged",
          "justification":"Reviewed the failed event and assigned an operator to investigate."}
    assert client.post(endpoint,json=data).status_code==401
    assert client.post(endpoint,json=data,headers=auth("manager")).status_code==403
    for forged in (
      {"department_id":"foreign"},{"actor_id":"forged"},{"clear_alert":True},
      {"issue_code":"mark_production_ready"},{"action":"resolved"},
      {"justification":"too short"},{"source_id":"../foreign"},
    ):
        assert client.post(endpoint,json={**data,**forged},headers=auth()).status_code==422
    with patch("app.api.v1.work_integrations.IntegrationOperationsRepository.record_response",
               return_value={"id":"ops_1","health_cleared":False}) as action:
        r=client.post(endpoint,json=data,headers=auth())
    assert r.status_code==201 and r.json()["health_cleared"] is False
    assert action.call_args.args==("receiving","a_1","warehouse-east","dead_outbound",
                                   "acknowledged",data["justification"])
    with patch("app.api.v1.work_integrations.IntegrationOperationsRepository.record_response",
               side_effect=OperationsNotFound()):
        assert client.post(endpoint,json=data,headers=auth()).status_code==404
    with patch("app.api.v1.work_integrations.IntegrationOperationsRepository.record_response",
               side_effect=OperationsConflict("Invalid remediation.")):
        assert client.post(endpoint,json=data,headers=auth()).status_code==409

def test_dashboard_alerts_are_grounded_and_per_source(monkeypatch):
    sample={
      "id":"warehouse-east","status":"active",
      "inbound_key_present":True,"outbound_target_ready":True,
      "dead_outbound":2,"stale_outbound":1,"expired_lease":0,
      "invalid_inbound_24h":3,"overdue_reviews":2,"overdue_receipts":0,
    }
    alert=_source_alerts(sample)
    assert {x["code"] for x in alert}=={
      "dead_outbound","stale_outbound","invalid_inbound","pending_review",
    }
    assert all(x["count"]>0 and x["source_id"]=="warehouse-east" for x in alert)
    clean={**sample,"dead_outbound":0,"stale_outbound":0,
      "invalid_inbound_24h":0,"overdue_reviews":0}
    assert _source_alerts(clean)==[]
    without={**clean,"inbound_key_present":False,"outbound_target_ready":False}
    assert {x["code"] for x in _source_alerts(without)}=={
      "signing_key_missing","outbound_unconfigured",
    }

def test_integration_readiness_never_trusts_placeholder_targets(monkeypatch):
    monkeypatch.setattr(settings,"WORKMATE_OUTBOUND_ENABLED",True)
    monkeypatch.setattr(settings,"WORKMATE_OUTBOUND_ALLOWED_HOSTS","approved.example.com")
    monkeypatch.setattr(settings,"WORKMATE_OUTBOUND_TARGETS_JSON",
      '{"warehouse-east":{"url":"http://approved.example.com/a","secret":"wrong-weak"}}')
    assert configured_target("warehouse-east") is None
