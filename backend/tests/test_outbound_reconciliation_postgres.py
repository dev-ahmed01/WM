"""Phase 6C PostgreSQL proof: acceptance/outbox atomic, leasing, dead letter,
authenticated receipt, human recovery and department RLS.
"""
from uuid import uuid4
import json
import hashlib
import psycopg
import pytest
import httpx

from app.core.config import settings
from app.repositories.work_integration_connector_repository import ConnectorRepository
from app.repositories.work_integration_intake_repository import IntegrationIntakeRepository,IntegrationConflict
from app.repositories.work_integration_outbox_repository import OutboxRepository,OutboxConflict,OutboxNotFound
from app.repositories.work_item_repository import WorkItemRepository
from app.services.work_integration_outbound import dispatch_claim


@pytest.mark.live_integration
def test_pg_reviewed_signed_work_outbox_retry_lease_dead_and_remote_ack(monkeypatch):
    k=uuid4().hex[:8]
    dept,foreign="ob_a_"+k,"ob_b_"+k
    submitter,reviewer,worker,outsider=[
        p+k for p in ("ob_src_","ob_rev_","ob_emp_","ob_foreign_")
    ]
    admin_role,worker_role="ob_role_a_"+k,"ob_role_e_"+k
    source_id="source_"+k
    ingress_secret="local-phase6c-inbound-signing-key-length-32"+k
    outbound_secret="local-phase6c-outbound-signing-key-length-32"+k
    monkeypatch.setattr(settings,"WORKMATE_CONNECTOR_SECRETS_JSON",json.dumps({source_id:ingress_secret}))
    monkeypatch.setattr(settings,"WORKMATE_OUTBOUND_TARGETS_JSON",json.dumps({
        source_id:{"url":"https://ack.example.net/workmate","secret":outbound_secret}
    }))
    monkeypatch.setattr(settings,"WORKMATE_OUTBOUND_ALLOWED_HOSTS","ack.example.net")
    monkeypatch.setattr(settings,"WORKMATE_OUTBOUND_ENABLED",True)
    intake_id=work_id=outbox_id=None
    with psycopg.connect(settings.DATABASE_URL,autocommit=True) as conn:
        with conn.cursor() as cur:
            for d in (dept,foreign):
                cur.execute("INSERT INTO security.departments(id,code,name) VALUES(%s,%s,%s)",(d,d.upper(),d))
            for role,name in ((admin_role,"admin"),(worker_role,"employee")):
                cur.execute("INSERT INTO security.roles(id,name,permission_set) VALUES(%s,%s,'{}'::jsonb)",(role,name))
            for actor,d in ((submitter,dept),(reviewer,dept),(worker,dept),(outsider,foreign)):
                cur.execute("""INSERT INTO security.users(id,email,hashed_password,department_id,status)
                               VALUES(%s,%s,'synthetic',%s,'active')""",(actor,actor+"@example.test",d))
            for actor,role in ((submitter,admin_role),(reviewer,admin_role),
                               (worker,worker_role),(outsider,admin_role)):
                cur.execute("INSERT INTO security.user_roles(user_id,role_id) VALUES(%s,%s)",(actor,role))
    try:
        ConnectorRepository.register(dept,submitter,source_id,"custom_wms")
        payload={
            "source_system":"custom_wms","external_event_id":"receiving.confirmed."+k,
            "external_work_id":"DOCK-"+k,"title":"Verify receiving order before putaway",
            "work_type":"receiving","priority":"high","instructions":"Follow approved receiving procedure.",
            "assigned_to":worker,
        }
        raw=json.dumps(payload).encode()
        source=ConnectorRepository.lookup_active(source_id)
        staged=ConnectorRepository.deliver(
            source,"nonce_first_"+k+"_"+uuid4().hex[:12],"1760000000",raw,payload)
        intake_id=staged["intake_id"]
        assert OutboxRepository.list(dept,submitter,source_id)==[]
        assert WorkItemRepository.list(dept,submitter,True)==[]
        # Preapproval imports cannot emit an ERP notice or create work.
        with pytest.raises(IntegrationConflict):
            IntegrationIntakeRepository.decide(dept,submitter,intake_id,"accepted",
                "Self-review must not create a task or outbound event.")
        assert OutboxRepository.list(dept,submitter,source_id)==[]
        accepted=IntegrationIntakeRepository.decide(dept,reviewer,intake_id,"accepted",
            "Separate reviewer reconciled the shipment against its dock purchase order.")
        work_id=accepted["work_item_id"]
        queued=WorkItemRepository.get(dept,reviewer,True,work_id)
        assert queued["status"]=="queued" and queued["workflow_version_id"] is None
        assert queued["execution_session_id"] is None
        events=OutboxRepository.list(dept,submitter,source_id)
        assert len(events)==1 and events[0]["status"]=="pending"
        outbox_id=events[0]["id"]
        assert events[0]["work_item_id"]==work_id
        with pytest.raises(OutboxNotFound):
            OutboxRepository.list(foreign,outsider,source_id)
        assert ConnectorRepository.set_enabled(dept,submitter,source_id,False)["status"]=="disabled"
        assert OutboxRepository.claim(1)==[]
        ConnectorRepository.set_enabled(dept,submitter,source_id,True)
        # Five attempts, all non-acknowledged, lead to dead-letter rather than
        # auto-unblocking a single SOP or altering the imported queued task.
        for n in range(1,6):
            claim=OutboxRepository.claim(1)
            assert len(claim)==1 and claim[0]["id"]==outbox_id
            job=claim[0]
            assert job["attempt"]==n
            assert not OutboxRepository.settle(outbox_id,"forged-token",False,
                                               reason="http_status")
            if n<5:
                assert OutboxRepository.settle(outbox_id,job["lease_token"],False,
                                               reason="transport_error")
                with psycopg.connect(settings.DATABASE_URL,autocommit=True) as conn:
                    conn.execute("""
                      UPDATE workmate_copilot.work_integration_outbox
                      SET next_attempt_at=CURRENT_TIMESTAMP-INTERVAL '1 second'
                      WHERE id=%s
                    """,(outbox_id,))
            else:
                # A crash after the fifth claim must not strand a leased event.
                # Simulate lease expiry without calling settle.
                with psycopg.connect(settings.DATABASE_URL,autocommit=True) as conn:
                    conn.execute("""
                      UPDATE workmate_copilot.work_integration_outbox
                      SET lease_expires_at=CURRENT_TIMESTAMP-INTERVAL '1 second'
                      WHERE id=%s
                    """,(outbox_id,))
                assert OutboxRepository.claim(1)==[]
        last=OutboxRepository.list(dept,submitter,source_id)[0]
        assert last["status"]=="dead" and last["attempts"]==5
        assert OutboxRepository.claim(1)==[]
        with pytest.raises(OutboxConflict):
            OutboxRepository.recover(dept,submitter,outbox_id,"short")
        with pytest.raises(OutboxNotFound):
            OutboxRepository.recover(foreign,outsider,outbox_id,
                "Cannot manage outbound work from another department.")
        recovery=OutboxRepository.recover(dept,submitter,outbox_id,
            "Partner endpoint outage resolved and manual replay reviewed.")
        assert recovery["recovered_count"]==1 and recovery["status"]=="pending"
        leased=OutboxRepository.claim(1)[0]
        seen=[]
        def remote(request):
            seen.append(request)
            assert request.url.host=="ack.example.net"
            assert request.headers["X-WM-Outbox-Id"]==outbox_id
            assert json.loads(request.content)["work_status"]=="queued"
            return httpx.Response(200,json={
                "event_id":outbox_id,"status":"accepted","receipt_id":"ERP-ACK-"+k,
            })
        assert dispatch_claim(leased,lambda:httpx.Client(transport=httpx.MockTransport(remote)))
        assert len(seen)==1
        after=OutboxRepository.list(dept,submitter,source_id)[0]
        assert after["status"]=="delivered" and after["ack_reference"]=="ERP-ACK-"+k
        assert after["attempts"]==1 and after["recovered_count"]==1
        with pytest.raises(OutboxConflict):
            OutboxRepository.recover(dept,submitter,outbox_id,
                "Delivered event must never be retried manually.")
        assert WorkItemRepository.get(dept,reviewer,True,work_id)["status"]=="queued"
        with psycopg.connect(settings.DATABASE_URL) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT count(*) FROM workmate_copilot.work_integration_outbox_attempts WHERE outbox_id=%s",(outbox_id,))
                assert cur.fetchone()[0]==6
                cur.execute("SELECT count(*) FROM workmate_copilot.work_integration_outbox_recoveries WHERE outbox_id=%s",(outbox_id,))
                assert cur.fetchone()[0]==1
                cur.execute("BEGIN")
                cur.execute("SET LOCAL ROLE workmate_scoped_reader")
                for table in ("work_integration_outbox","work_integration_outbox_attempts",
                              "work_integration_outbox_recoveries"):
                    cur.execute(f"SELECT count(*) FROM workmate_copilot.{table} WHERE department_id=%s",(dept,))
                    assert cur.fetchone()[0]==0
                cur.execute("SELECT set_config('workmate.department_id',%s,true)",(dept,))
                cur.execute("SELECT count(*) FROM workmate_copilot.work_integration_outbox WHERE id=%s",(outbox_id,))
                assert cur.fetchone()[0]==1
                cur.execute("ROLLBACK")
    finally:
        with psycopg.connect(settings.DATABASE_URL,autocommit=True) as conn:
            with conn.cursor() as cur:
                if outbox_id:
                    for table in ("work_integration_outbox_attempts","work_integration_outbox_recoveries"):
                        cur.execute(f"DELETE FROM workmate_copilot.{table} WHERE outbox_id=%s",(outbox_id,))
                    cur.execute("DELETE FROM workmate_copilot.work_integration_outbox WHERE id=%s",(outbox_id,))
                cur.execute("DELETE FROM workmate_copilot.work_integration_deliveries WHERE source_id=%s",(source_id,))
                if intake_id:
                    cur.execute("DELETE FROM workmate_copilot.work_integration_intake WHERE id=%s",(intake_id,))
                if work_id:
                    cur.execute("DELETE FROM workmate_copilot.work_item_events WHERE work_item_id=%s",(work_id,))
                    cur.execute("DELETE FROM workmate_copilot.work_items WHERE id=%s",(work_id,))
                cur.execute("DELETE FROM workmate_copilot.work_integration_sources WHERE id=%s",(source_id,))
                cur.execute("DELETE FROM security.user_roles WHERE role_id IN (%s,%s)",(admin_role,worker_role))
                cur.execute("DELETE FROM security.users WHERE id=ANY(%s)",([submitter,reviewer,worker,outsider],))
                cur.execute("DELETE FROM security.roles WHERE id IN (%s,%s)",(admin_role,worker_role))
                cur.execute("DELETE FROM security.departments WHERE id=ANY(%s)",([dept,foreign],))
