"""Phase 6D live PostgreSQL: true 24h health, response audit and RLS boundaries."""
import json
from uuid import uuid4

import psycopg
import pytest

from app.core.config import settings
from app.repositories.work_integration_connector_repository import ConnectorRepository
from app.repositories.work_integration_intake_repository import IntegrationIntakeRepository
from app.repositories.work_integration_operations_repository import (
    IntegrationOperationsRepository,OperationsNotFound,OperationsConflict,
)

@pytest.mark.live_integration
def test_integration_ops_real_alerts_human_actions_and_rls(monkeypatch):
    k=uuid4().hex[:9]
    dept,foreign="ops_a_"+k,"ops_b_"+k
    author,reviewer,outsider=["ops_"+p+k for p in ("author_","review_","foreign_")]
    role="ops_role_"+k
    source="ops_source_"+k
    monkeypatch.setattr(settings,"WORKMATE_CONNECTOR_SECRETS_JSON",
        json.dumps({source:"local-signing-key-with-at-least-32-characters-"+k}))
    monkeypatch.setattr(settings,"WORKMATE_OUTBOUND_ENABLED",False)
    entry=None
    with psycopg.connect(settings.DATABASE_URL,autocommit=True) as conn:
        with conn.cursor() as cur:
            for d in (dept,foreign):
                cur.execute("INSERT INTO security.departments(id,code,name) VALUES(%s,%s,%s)",(d,d.upper(),d))
            cur.execute("INSERT INTO security.roles(id,name,permission_set) VALUES(%s,'admin','{}'::jsonb)",(role,))
            for actor,d in ((author,dept),(reviewer,dept),(outsider,foreign)):
                cur.execute("""INSERT INTO security.users(id,email,hashed_password,department_id,status)
                  VALUES(%s,%s,'synthetic',%s,'active')""",(actor,actor+"@example.test",d))
                cur.execute("INSERT INTO security.user_roles(user_id,role_id) VALUES(%s,%s)",(actor,role))
    try:
        empty=IntegrationOperationsRepository.snapshot(dept,author)
        assert empty["decision"]=="NO_GO"
        assert empty["operational_status"]=="not_configured"
        assert empty["counts"]["sources"]==0
        ConnectorRepository.register(dept,author,source,"custom_wms")
        ready=IntegrationOperationsRepository.snapshot(dept,reviewer)
        assert ready["decision"]=="NO_GO"
        assert ready["field_verification"]=="not_automatically_verified"
        assert ready["counts"]["sources"]==1 and ready["counts"]["active_sources"]==1
        assert {a["code"] for a in ready["alerts"]}=={"outbound_unconfigured"}
        incoming={
            "source_system":"custom_wms","external_event_id":"dock.received."+k,
            "external_work_id":"DOCK-"+k,"title":"Inspect cold-chain shipment at dock",
            "work_type":"receiving","priority":"high",
            "instructions":"Check seal, temperature and receiving reference.",
            "assigned_to":None,
        }
        raw=json.dumps(incoming).encode()
        result=ConnectorRepository.deliver(
            ConnectorRepository.lookup_active(source),
            "ops_nonce_"+k+"_"+uuid4().hex[:12],
            "1760000000",raw,incoming,
        )
        entry=result["intake_id"]
        invalid=ConnectorRepository.deliver(
            ConnectorRepository.lookup_active(source),
            "bad_nonce_"+k+"_"+uuid4().hex[:12],
            "1760000000",b'{"unknown":true}',None,"invalid_schema",
        )
        assert invalid["status"]=="invalid"
        with psycopg.connect(settings.DATABASE_URL,autocommit=True) as conn:
            conn.execute("""
              UPDATE workmate_copilot.work_integration_intake
              SET created_at=CURRENT_TIMESTAMP-INTERVAL '26 hours'
              WHERE id=%s
            """,(entry,))
        health=IntegrationOperationsRepository.snapshot(dept,reviewer)
        assert health["counts"]["inbound_24h"]==2
        assert health["counts"]["outbound_acks_24h"]==0
        assert {alert["code"] for alert in health["alerts"]}=={
            "outbound_unconfigured","pending_review","invalid_inbound",
        }
        assert health["sources"][0]["overdue_reviews"]==1
        action=IntegrationOperationsRepository.record_response(
            dept,reviewer,source,"pending_review","acknowledged",
            "Reviewed the pending receiving order and scheduled independent operator action.",
        )
        assert action["health_cleared"] is False
        action_again=IntegrationOperationsRepository.record_response(
            dept,reviewer,source,"invalid_inbound","remediation_logged",
            "Investigated invalid source event schema and escalated connector repair.",
        )
        assert action_again["action"]=="remediation_logged"
        snapshot=IntegrationOperationsRepository.snapshot(dept,reviewer)
        assert len(snapshot["latest_actions"])==2
        assert snapshot["latest_actions"][0]["actor_id"]==reviewer
        assert "pending_review" in {a["code"] for a in snapshot["alerts"]}
        with pytest.raises(OperationsNotFound):
            IntegrationOperationsRepository.record_response(
                foreign,outsider,source,"pending_review","acknowledged",
                "A foreign department must not acknowledge another team's issues.",
            )
        with pytest.raises(OperationsConflict):
            IntegrationOperationsRepository.record_response(
                dept,author,source,"unblock_work","acknowledged",
                "No operator may invent an authority to release held work.",
            )
        with psycopg.connect(settings.DATABASE_URL) as conn:
            with conn.cursor() as cur:
                cur.execute("BEGIN")
                cur.execute("SET LOCAL ROLE workmate_scoped_reader")
                cur.execute("""
                  SELECT COUNT(*) FROM workmate_copilot.work_integration_operator_actions
                  WHERE source_id=%s
                """,(source,))
                assert cur.fetchone()[0]==0
                cur.execute("SELECT set_config('workmate.department_id',%s,true)",(foreign,))
                cur.execute("""
                  SELECT COUNT(*) FROM workmate_copilot.work_integration_operator_actions
                  WHERE source_id=%s
                """,(source,))
                assert cur.fetchone()[0]==0
                cur.execute("SELECT set_config('workmate.department_id',%s,true)",(dept,))
                cur.execute("""
                  SELECT COUNT(*) FROM workmate_copilot.work_integration_operator_actions
                  WHERE source_id=%s
                """,(source,))
                assert cur.fetchone()[0]==2
                cur.execute("ROLLBACK")
        ConnectorRepository.set_enabled(dept,author,source,False)
        blocked=IntegrationOperationsRepository.snapshot(dept,author)
        assert "connector_disabled" in {a["code"] for a in blocked["alerts"]}
        assert blocked["decision"]=="NO_GO"
    finally:
        with psycopg.connect(settings.DATABASE_URL,autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute("""
                  DELETE FROM workmate_copilot.work_integration_operator_actions WHERE source_id=%s
                """,(source,))
                cur.execute("DELETE FROM workmate_copilot.work_integration_deliveries WHERE source_id=%s",(source,))
                if entry:
                    cur.execute("DELETE FROM workmate_copilot.work_integration_intake WHERE id=%s",(entry,))
                cur.execute("DELETE FROM workmate_copilot.work_integration_sources WHERE id=%s",(source,))
                cur.execute("DELETE FROM security.user_roles WHERE role_id=%s",(role,))
                cur.execute("DELETE FROM security.users WHERE id=ANY(%s)",([author,reviewer,outsider],))
                cur.execute("DELETE FROM security.roles WHERE id=%s",(role,))
                cur.execute("DELETE FROM security.departments WHERE id=ANY(%s)",([dept,foreign],))
