"""Phase 6B real PostgreSQL acceptance for registered signed source lifecycles."""
import hashlib
import hmac
import json
import time
from uuid import uuid4

import psycopg
import pytest

from app.core.config import settings
from app.repositories.work_integration_connector_repository import (
    ConnectorRepository,is_signature_valid,IntegrationConflict,IntegrationNotFound,
)
from app.repositories.work_integration_intake_repository import IntegrationIntakeRepository
from app.repositories.work_item_repository import WorkItemRepository


@pytest.mark.live_integration
def test_signed_connector_nonce_diagnostics_review_and_tenant_separation(monkeypatch):
    k=uuid4().hex[:9]
    dep,other="wh_a_"+k,"wh_b_"+k
    author,approver,worker,stranger=[
        p+k for p in ("wh_admin_","wh_approver_","wh_worker_","wh_other_")
    ]
    manager_role="wh_adminrole_"+k
    employee_role="wh_emprole_"+k
    connector="wh_"+k
    secret="phase6b-local-secret-has-strong-length-xxxxxxxx"+k
    monkeypatch.setattr(settings,"WORKMATE_CONNECTOR_SECRETS_JSON",json.dumps({connector:secret}))
    assigned=None
    entry=None
    with psycopg.connect(settings.DATABASE_URL,autocommit=True) as conn:
        with conn.cursor() as cur:
            for d in (dep,other):
                cur.execute("INSERT INTO security.departments(id,code,name) VALUES(%s,%s,%s)",(d,d.upper(),d))
            for role,name in ((manager_role,"admin"),(employee_role,"employee")):
                cur.execute("INSERT INTO security.roles(id,name,permission_set) VALUES(%s,%s,'{}'::jsonb)",(role,name))
            for uid,d in ((author,dep),(approver,dep),(worker,dep),(stranger,other)):
                cur.execute("""INSERT INTO security.users(id,email,hashed_password,department_id,status)
                    VALUES(%s,%s,'synthetic',%s,'active')""",(uid,uid+"@example.test",d))
            for uid,role in ((author,manager_role),(approver,manager_role),(worker,employee_role),(stranger,manager_role)):
                cur.execute("INSERT INTO security.user_roles(user_id,role_id) VALUES(%s,%s)",(uid,role))
    try:
        registered=ConnectorRepository.register(dep,author,connector,"custom_wms")
        assert registered["status"]=="active"
        with pytest.raises(IntegrationConflict):
            ConnectorRepository.register(dep,author,connector,"custom_wms")
        with pytest.raises(IntegrationConflict):
            ConnectorRepository.register(dep,author,"missingconnector","custom_wms")
        assert ConnectorRepository.lookup_active(connector)["department_id"]==dep
        assert len(ConnectorRepository.list(dep,author))==1
        assert ConnectorRepository.list(other,stranger)==[]
        data={
            "source_system":"custom_wms","external_event_id":"receipt.received."+k,
            "external_work_id":"RECEIPT-"+k,"title":"Inspect inbound signed WMS cartons",
            "work_type":"receiving","priority":"high","instructions":"Compare the receiving lot.",
            "assigned_to":worker,
        }
        raw=json.dumps(data,separators=(",",":")).encode()
        stamp=str(int(time.time()))
        nonce="test_nonce_"+k+"_"+uuid4().hex[:12]
        signature="v1="+hmac.new(secret.encode(),
            b"v1\n"+stamp.encode()+b"\n"+nonce.encode()+b"\n"+raw,
            hashlib.sha256).hexdigest()
        assert is_signature_valid(secret.encode(),stamp,nonce,raw,signature)
        source=ConnectorRepository.lookup_active(connector)
        delivered=ConnectorRepository.deliver(source,nonce,stamp,raw,data)
        entry=delivered["intake_id"]
        assert delivered["status"]=="staged" and not delivered["replayed"]
        assert WorkItemRepository.list(dep,approver,True)==[]
        with pytest.raises(IntegrationConflict):
            ConnectorRepository.deliver(source,nonce,stamp,raw,data)
        next_nonce="retry_nonce_"+k+"_"+uuid4().hex[:12]
        retry=ConnectorRepository.deliver(source,next_nonce,stamp,raw,data)
        assert retry["status"]=="replayed" and retry["intake_id"]==entry
        mismatch=ConnectorRepository.deliver(
            source,"mismatch_nonce_"+k+"_"+uuid4().hex[:12],stamp,raw,
            {**data,"source_system":"sap"}
        )
        assert mismatch["status"]=="invalid" and mismatch["reason_code"]=="source_mismatch"
        conflict=ConnectorRepository.deliver(
            source,"collision_nonce_"+k+"_"+uuid4().hex[:12],stamp,raw,
            {**data,"external_event_id":"changed."+k}
        )
        assert conflict["status"]=="conflict" and conflict["reason_code"]=="source_collision"
        invalid=ConnectorRepository.deliver(
            source,"invalid_nonce_"+k+"_"+uuid4().hex[:12],stamp,b'{"oops":1}',None,
            "invalid_schema"
        )
        assert invalid["status"]=="invalid" and invalid["intake_id"] is None
        health=ConnectorRepository.list(dep,author)[0]
        assert health["deliveries"]==5 and health["failures"]==3
        events=ConnectorRepository.deliveries(dep,author,connector,limit=8)
        assert len(events)==5 and all("request_nonce" not in item for item in events)
        with pytest.raises(IntegrationNotFound):
            ConnectorRepository.deliveries(other,stranger,connector)
        intake=IntegrationIntakeRepository.list(dep,approver)
        assert len(intake)==1 and intake[0]["submitted_by"]==author
        accepted=IntegrationIntakeRepository.decide(dep,approver,entry,"accepted",
            "Independent administrator reconciled source shipment to dock receiving order.")
        assigned=accepted["work_item_id"]
        item=WorkItemRepository.get(dep,approver,True,assigned)
        assert item["status"]=="queued" and item["execution_session_id"] is None
        assert item["workflow_version_id"] is None
        ConnectorRepository.set_enabled(dep,author,connector,False)
        assert ConnectorRepository.lookup_active(connector) is None
        with pytest.raises(IntegrationNotFound):
            ConnectorRepository.deliver(source,
                "disabled_nonce_"+k+"_"+uuid4().hex[:12],stamp,raw,data)
        ConnectorRepository.set_enabled(dep,author,connector,True)
        assert ConnectorRepository.lookup_active(connector)
        with psycopg.connect(settings.DATABASE_URL) as conn:
            with conn.cursor() as cur:
                cur.execute("BEGIN")
                cur.execute("SET LOCAL ROLE workmate_scoped_reader")
                cur.execute("SELECT count(*) FROM workmate_copilot.work_integration_deliveries WHERE source_id=%s",(connector,))
                assert cur.fetchone()[0]==0
                cur.execute("SELECT set_config('workmate.department_id',%s,true)",(other,))
                cur.execute("SELECT count(*) FROM workmate_copilot.work_integration_deliveries WHERE source_id=%s",(connector,))
                assert cur.fetchone()[0]==0
                cur.execute("SELECT set_config('workmate.department_id',%s,true)",(dep,))
                cur.execute("SELECT count(*) FROM workmate_copilot.work_integration_deliveries WHERE source_id=%s",(connector,))
                assert cur.fetchone()[0]==5
                cur.execute("ROLLBACK")
    finally:
        with psycopg.connect(settings.DATABASE_URL,autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM workmate_copilot.work_integration_deliveries WHERE source_id=%s",(connector,))
                if entry:
                    cur.execute("DELETE FROM workmate_copilot.work_integration_intake WHERE id=%s",(entry,))
                if assigned:
                    cur.execute("DELETE FROM workmate_copilot.work_item_events WHERE work_item_id=%s",(assigned,))
                    cur.execute("DELETE FROM workmate_copilot.work_items WHERE id=%s",(assigned,))
                cur.execute("DELETE FROM workmate_copilot.work_integration_sources WHERE id=%s",(connector,))
                cur.execute("DELETE FROM security.user_roles WHERE role_id IN (%s,%s)",(manager_role,employee_role))
                cur.execute("DELETE FROM security.users WHERE id=ANY(%s)",([author,approver,worker,stranger],))
                cur.execute("DELETE FROM security.roles WHERE id IN (%s,%s)",(manager_role,employee_role))
                cur.execute("DELETE FROM security.departments WHERE id=ANY(%s)",([dep,other],))
