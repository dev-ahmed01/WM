"""Phase 6B unit/API safety checks for HMAC ingress and connector controls."""
import hashlib
import hmac
import json
import time
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.core.config import settings
from app.core.security import create_access_token
from app.repositories.work_integration_connector_repository import (
    is_signature_valid,configured_secret,MAX_BODY,
)
from app.repositories.work_integration_intake_repository import IntegrationNotFound

client=TestClient(app)
SOURCE="phase6b_source"
SECRET="this-is-a-controlled-phase6b-signing-secret-strong-enough"
PAYLOAD={
    "source_system":"custom_wms","external_event_id":"shipment.received.6205",
    "external_work_id":"SHIP-6205","title":"Check incoming shipment seals",
    "work_type":"receiving","priority":"high","instructions":"Check carton seal condition.",
    "assigned_to":None,
}


def auth(role="admin",department="receiving",actor="admin1"):
    return {"Authorization":"Bearer "+create_access_token(actor,role,department)}


def signed(raw,nonce="phase6b_nonce_000001",timestamp=None):
    stamp=str(int(time.time()) if timestamp is None else timestamp)
    canonical=b"v1\n"+stamp.encode()+b"\n"+nonce.encode()+b"\n"+raw
    return {
        "X-WM-Timestamp":stamp,"X-WM-Nonce":nonce,
        "X-WM-Signature":"v1="+hmac.new(SECRET.encode(),canonical,hashlib.sha256).hexdigest(),
        "Content-Type":"application/json",
    }


def test_hmac_auth_requires_configured_long_secret_fresh_nonce_and_exact_raw_bytes(monkeypatch):
    monkeypatch.setattr(settings,"WORKMATE_CONNECTOR_SECRETS_JSON",
        json.dumps({SOURCE:SECRET,"short":"weak"}))
    assert configured_secret(SOURCE)==SECRET.encode()
    assert configured_secret("short") is None
    body=json.dumps(PAYLOAD).encode()
    head=signed(body)
    assert is_signature_valid(SECRET.encode(),head["X-WM-Timestamp"],
                              head["X-WM-Nonce"],body,head["X-WM-Signature"])
    assert not is_signature_valid(SECRET.encode(),head["X-WM-Timestamp"],
                                  head["X-WM-Nonce"],body+b" ",head["X-WM-Signature"])
    assert not is_signature_valid(SECRET.encode(),head["X-WM-Timestamp"],
                                  head["X-WM-Nonce"],body,"v1="+"0"*64)
    assert not is_signature_valid(SECRET.encode(),str(int(time.time())-1200),
                                  head["X-WM-Nonce"],body,head["X-WM-Signature"])
    assert not is_signature_valid(SECRET.encode(),head["X-WM-Timestamp"],
                                  "not-valid",body,head["X-WM-Signature"])
    assert not is_signature_valid(SECRET.encode(),head["X-WM-Timestamp"],
                                  head["X-WM-Nonce"],b"x"*(MAX_BODY+1),head["X-WM-Signature"])


def test_webhook_without_jwt_stages_only_verified_bounded_payload(monkeypatch):
    monkeypatch.setattr(settings,"WORKMATE_CONNECTOR_SECRETS_JSON",json.dumps({SOURCE:SECRET}))
    url="/api/v1/work/integrations/webhooks/"+SOURCE
    raw=json.dumps(PAYLOAD).encode()
    source={"id":SOURCE,"department_id":"receiving",
            "source_system":"custom_wms","created_by":"admin1"}
    assert client.post(url,content=raw).status_code==401
    bad=client.post(url,content=raw,headers=signed(raw,timestamp=int(time.time())-700))
    assert bad.status_code==401
    assert client.post(url,content=raw+b" ",headers=signed(raw)).status_code==401
    assert client.post(url,content=b"x"*(MAX_BODY+1),headers=signed(b"x"*(MAX_BODY+1))).status_code==413
    with patch("app.api.v1.work_integrations.ConnectorRepository.lookup_active",return_value=source):
        with patch("app.api.v1.work_integrations.ConnectorRepository.deliver",return_value={
            "delivery_id":"del_1","status":"staged","reason_code":"none","intake_id":"int_1",
            "replayed":False,
        }) as delivered:
            response=client.post(url,content=raw,headers=signed(raw))
    assert response.status_code==202 and response.json()["intake_id"]=="int_1"
    args=delivered.call_args.args
    assert args[0]==source and args[3]==raw
    assert args[4]["source_system"]=="custom_wms"
    assert "department_id" not in args[4]
    assert args[5] is None


def test_signed_invalid_payload_is_diagnostic_not_auto_queue(monkeypatch):
    monkeypatch.setattr(settings,"WORKMATE_CONNECTOR_SECRETS_JSON",json.dumps({SOURCE:SECRET}))
    url="/api/v1/work/integrations/webhooks/"+SOURCE
    raw=json.dumps({**PAYLOAD,"release_hold":True}).encode()
    source={"id":SOURCE,"department_id":"receiving",
            "source_system":"custom_wms","created_by":"admin1"}
    with patch("app.api.v1.work_integrations.ConnectorRepository.lookup_active",return_value=source):
        with patch("app.api.v1.work_integrations.ConnectorRepository.deliver",return_value={
            "delivery_id":"del_2","status":"invalid","reason_code":"invalid_schema",
            "intake_id":None,"replayed":False
        }) as record:
            response=client.post(url,content=raw,headers=signed(raw))
    assert response.status_code==422
    assert record.call_args.args[4] is None and record.call_args.args[5]=="invalid_schema"
    with patch("app.api.v1.work_integrations.ConnectorRepository.lookup_active",return_value=None):
        denied=client.post(url,content=raw,headers=signed(raw))
    assert denied.status_code==401


def test_admin_controls_require_role_and_keep_preconfigured_secrets_private():
    url="/api/v1/work/integrations/sources"
    creation={"id":SOURCE,"source_system":"custom_wms"}
    assert client.post(url,json=creation).status_code==401
    assert client.post(url,headers=auth("employee"),json=creation).status_code==403
    for injected in ({"secret":"attacker-key"},{"department_id":"other"},
                     {"created_by":"other"},{"source_system":"firewall"},
                     {"id":"!not-url-safe"}):
        assert client.post(url,headers=auth(),json={**creation,**injected}).status_code==422
    with patch("app.api.v1.work_integrations.ConnectorRepository.register",
               return_value={"id":SOURCE,"status":"active"}) as register:
        result=client.post(url,headers=auth(),json=creation)
    assert result.status_code==201
    assert register.call_args.args==("receiving","admin1",SOURCE,"custom_wms")
    with patch("app.api.v1.work_integrations.ConnectorRepository.list",
               return_value=[{"id":SOURCE,"status":"active"}]) as listing:
        result=client.get(url,headers=auth())
    assert result.status_code==200
    assert listing.call_args.args==("receiving","admin1")
    assert client.get(url,headers=auth("manager")).status_code==403
    with patch("app.api.v1.work_integrations.ConnectorRepository.set_enabled",
               return_value={"id":SOURCE,"status":"disabled"}) as control:
        disabled=client.post(url+"/"+SOURCE+"/control",headers=auth(),json={"enabled":False})
    assert disabled.status_code==200
    assert control.call_args.args==("receiving","admin1",SOURCE,False)
    with patch("app.api.v1.work_integrations.ConnectorRepository.deliveries",
               return_value=[{"id":"del_1","status":"staged"}]) as ledger:
        health=client.get(url+"/"+SOURCE+"/deliveries?limit=10",headers=auth())
    assert health.status_code==200 and len(health.json()["items"])==1
    assert ledger.call_args.args==("receiving","admin1",SOURCE,10)
    with patch("app.api.v1.work_integrations.ConnectorRepository.list",
               side_effect=IntegrationNotFound()):
        assert client.get(url,headers=auth()).status_code==404
