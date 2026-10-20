"""Phase 6C outbound worker: configured host safety, signed request, explicit ACK."""
import hashlib
import hmac
import json
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient
from app.core.config import settings
from app.core.security import create_access_token
from app.main import app
from app.services.work_integration_outbound import (
    configured_target,delivery_headers,dispatch_claim,dispatch_batch,
)
from app.repositories.work_integration_outbox_repository import OutboxConflict,OutboxNotFound

client=TestClient(app)
SRC="unit_erp_source_001"
SECRET="this-is-a-separate-long-outbound-secret-xxxxxxxx"
URL="https://receipt.partner.example/workmate/events"
JOB={"id":"out_unit_01","source_id":SRC,"department_id":"receiving",
     "lease_token":"one-time-job-lease-token","attempt":1,
     "payload":{"event_id":"out_unit_01","event_type":"work_accepted","work_status":"queued",
                "work_item_id":"wrk_unit"}}

def auth(role="admin",department="receiving",actor="admin_1"):
    return {"Authorization":"Bearer "+create_access_token(actor,role,department)}

def setup_config(monkeypatch,url=URL,hosts="receipt.partner.example",secret=SECRET):
    monkeypatch.setattr(settings,"WORKMATE_OUTBOUND_ENABLED",True)
    monkeypatch.setattr(settings,"WORKMATE_OUTBOUND_ALLOWED_HOSTS",hosts)
    monkeypatch.setattr(settings,"WORKMATE_OUTBOUND_TARGETS_JSON",
        json.dumps({SRC:{"url":url,"secret":secret}}))

def test_outbound_default_off_and_explicit_allowlisted_https(monkeypatch):
    monkeypatch.setattr(settings,"WORKMATE_OUTBOUND_ENABLED",False)
    with patch("app.services.work_integration_outbound.OutboxRepository.claim") as claim:
        assert dispatch_batch()=={"enabled":False,"claimed":0,"settled":0}
        claim.assert_not_called()
    setup_config(monkeypatch)
    assert configured_target(SRC)["url"]==URL
    for unsafe in (
        "http://receipt.partner.example/workmate/events",
        "https://127.0.0.1/workmate/events",
        "https://localhost/workmate/events",
        "https://receipt.partner.example:444/workmate/events",
        "https://user:password@receipt.partner.example/workmate/events",
        "https://receipt.partner.example/workmate/events#fragment",
        "https://receipt.partner.example.evil.test/workmate/events",
        "https://receipt.partner.example\\@evil.test/workmate/events",
    ):
        setup_config(monkeypatch,url=unsafe)
        assert configured_target(SRC) is None,unsafe
    setup_config(monkeypatch,hosts="other.partner.example")
    assert configured_target(SRC) is None
    setup_config(monkeypatch,secret="weak")
    assert configured_target(SRC) is None

def test_worker_only_marks_delivered_on_correlated_explicit_ack(monkeypatch):
    setup_config(monkeypatch)
    req=[]
    def handler(request):
        req.append(request)
        body=request.content
        signed=(b"v1\n"+request.headers["X-WM-Timestamp"].encode()+b"\n"
                +JOB["id"].encode()+b"\n"+body)
        expect="v1="+hmac.new(SECRET.encode(),signed,hashlib.sha256).hexdigest()
        assert request.headers["X-WM-Signature"]==expect
        assert request.url.host=="receipt.partner.example"
        assert json.loads(body)["work_status"]=="queued"
        return httpx.Response(200,json={"event_id":JOB["id"],"status":"accepted",
                                        "receipt_id":"ACK-UNIT-9001"})
    factory=lambda: httpx.Client(transport=httpx.MockTransport(handler))
    with patch("app.services.work_integration_outbound.OutboxRepository.settle",return_value=True) as settle:
        assert dispatch_claim(JOB,factory)
    assert len(req)==1 and settle.call_args.args[:3]==(JOB["id"],JOB["lease_token"],True)
    assert settle.call_args.kwargs["receipt"]=="ACK-UNIT-9001"

def test_retries_on_transport_rejection_and_missing_ack(monkeypatch):
    setup_config(monkeypatch)
    def run(handler):
        factory=lambda: httpx.Client(transport=httpx.MockTransport(handler))
        with patch("app.services.work_integration_outbound.OutboxRepository.settle",return_value=True) as settle:
            assert dispatch_claim(JOB,factory) is True
        assert settle.call_args.args[2] is False
        return settle.call_args.kwargs["reason"]
    assert run(lambda req:httpx.Response(500,json={"status":"accepted"}))=="http_status"
    assert run(lambda req:httpx.Response(200,json={"status":"accepted","event_id":"out_other",
        "receipt_id":"ACK-WRONG"}))=="invalid_ack"
    assert run(lambda req:httpx.Response(302,headers={"Location":"https://internal.example/"}))=="http_status"
    assert run(lambda req:httpx.Response(200,text="ACK-UNVERIFIED"))=="invalid_ack"
    assert run(lambda req:httpx.Response(200,content=b"x"*6000,headers={"content-type":"application/json"}))=="invalid_ack"
    def unreachable(req):raise httpx.ConnectError("blocked")
    assert run(unreachable)=="transport_error"
    setup_config(monkeypatch,hosts="not-allowed.test")
    with patch("app.services.work_integration_outbound.OutboxRepository.settle",return_value=True) as settle:
        assert dispatch_claim(JOB) is True
    assert settle.call_args.kwargs["reason"]=="not_configured"

def test_outbox_admin_scoping_and_recovery_endpoint():
    url="/api/v1/work/integrations/sources/"+SRC+"/outbox"
    assert client.get(url).status_code==401
    assert client.get(url,headers=auth("manager")).status_code==403
    with patch("app.api.v1.work_integrations.OutboxRepository.list",
               return_value=[{"id":"out_1","status":"pending"}]) as get:
        r=client.get(url+"?limit=3",headers=auth())
    assert r.status_code==200 and len(r.json()["items"])==1
    assert get.call_args.args==( "receiving","admin_1",SRC,3)
    endpoint="/api/v1/work/integrations/outbox/out_1/recover"
    data={"justification":"Endpoint credentials corrected and retry reviewed by supervisor."}
    assert client.post(endpoint,json=data,headers=auth("employee")).status_code==403
    for forged in ({"status":"delivered"},{"ack":"FAKE"},{"department_id":"other"},
                   {"justification":"short"}):
        assert client.post(endpoint,json={**data,**forged},headers=auth()).status_code==422
    with patch("app.api.v1.work_integrations.OutboxRepository.recover",
               return_value={"id":"out_1","status":"pending"}) as recover:
        result=client.post(endpoint,json=data,headers=auth())
    assert result.status_code==200
    assert recover.call_args.args==("receiving","admin_1","out_1",data["justification"])
    with patch("app.api.v1.work_integrations.OutboxRepository.recover",
               side_effect=OutboxConflict("No dead delivery.")):
        assert client.post(endpoint,json=data,headers=auth()).status_code==409
    with patch("app.api.v1.work_integrations.OutboxRepository.recover",
               side_effect=OutboxNotFound()):
        assert client.post(endpoint,json=data,headers=auth()).status_code==404
