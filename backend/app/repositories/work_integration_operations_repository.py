"""Phase 6D — actionable integration operations, never a self-authorizing pilot GO.

Counts are department-scoped, computed from committed PostgreSQL work/receipts.
No fabricated uptime, field evidence, third-party validation, or inferred
security posture from checked-in config.
"""
from __future__ import annotations
from uuid import uuid4

from app.core.config import settings
from app.core.database import get_postgres_connection
from app.repositories.work_integration_connector_repository import configured_secret
from app.services.work_integration_outbound import configured_target

ALERT_CODES={
    "dead_outbound","stale_outbound","expired_lease","invalid_inbound",
    "pending_review","signing_key_missing","outbound_unconfigured",
    "connector_disabled","no_recent_receipt",
}
ISSUE_LABELS={
    "dead_outbound":"Outbound deliveries need recovery",
    "stale_outbound":"Queued acknowledgements are overdue",
    "expired_lease":"A delivery worker lease expired",
    "invalid_inbound":"Signed incoming deliveries were rejected",
    "pending_review":"Warehouse imports await human approval",
    "signing_key_missing":"Inbound signing key is unavailable",
    "outbound_unconfigured":"Outbound delivery is not configured",
    "connector_disabled":"Connector is disabled",
    "no_recent_receipt":"Partner acknowledgements are overdue",
}
SEVERITY={
    "dead_outbound":"critical","stale_outbound":"high",
    "expired_lease":"high","invalid_inbound":"high",
    "pending_review":"high","signing_key_missing":"critical",
    "outbound_unconfigured":"high","connector_disabled":"high",
    "no_recent_receipt":"high",
}


class OperationsNotFound(Exception):
    pass


class OperationsConflict(Exception):
    pass


def _start(cur,dept):
    cur.execute("BEGIN")
    cur.execute("SELECT set_config('workmate.department_id',%s,true)",(dept,))


def _active_admin(cur,dept,actor):
    cur.execute("""
      SELECT 1 FROM security.users u
      JOIN security.user_roles ur ON ur.user_id=u.id
      JOIN security.roles role ON role.id=ur.role_id
      WHERE u.id=%s AND u.department_id=%s AND u.status='active'
        AND LOWER(role.name)='admin'
    """,(actor,dept))
    return cur.fetchone() is not None


def _source_alerts(source):
    alerts=[]
    for code,count in (
        ("connector_disabled",int(source["status"]!="active")),
        ("signing_key_missing",int(not source["inbound_key_present"])),
        ("outbound_unconfigured",int(not source["outbound_target_ready"])),
        ("dead_outbound",source["dead_outbound"]),
        ("stale_outbound",source["stale_outbound"]),
        ("expired_lease",source["expired_lease"]),
        ("invalid_inbound",source["invalid_inbound_24h"]),
        ("pending_review",source["overdue_reviews"]),
        ("no_recent_receipt",source["overdue_receipts"]),
    ):
        if count:
            alerts.append({"code":code,"severity":SEVERITY[code],
                           "count":int(count),"label":ISSUE_LABELS[code],
                           "source_id":source["id"]})
    return alerts


class IntegrationOperationsRepository:
    @staticmethod
    def snapshot(dept,actor):
        with get_postgres_connection() as conn:
            with conn.cursor() as cur:
                _start(cur,dept)
                try:
                    if not _active_admin(cur,dept,actor):
                        raise OperationsNotFound()
                    cur.execute("""
                      SELECT s.id,s.source_system,s.status,
                        (SELECT COUNT(*) FROM workmate_copilot.work_integration_deliveries d
                         WHERE d.department_id=s.department_id AND d.source_id=s.id
                           AND d.received_at>=CURRENT_TIMESTAMP-INTERVAL '24 hours') AS inbound_24h,
                        (SELECT COUNT(*) FROM workmate_copilot.work_integration_deliveries d
                         WHERE d.department_id=s.department_id AND d.source_id=s.id
                           AND d.status IN ('invalid','conflict')
                           AND d.received_at>=CURRENT_TIMESTAMP-INTERVAL '24 hours') AS invalid_inbound_24h,
                        (SELECT COUNT(*) FROM workmate_copilot.work_integration_intake i
                         WHERE i.department_id=s.department_id AND i.status='pending'
                           AND i.created_at<CURRENT_TIMESTAMP-INTERVAL '24 hours'
                           AND EXISTS(
                             SELECT 1 FROM workmate_copilot.work_integration_deliveries d
                             WHERE d.intake_id=i.id AND d.department_id=i.department_id
                               AND d.source_id=s.id AND d.status IN ('staged','replayed'))
                        ) AS overdue_reviews,
                        (SELECT COUNT(*) FROM workmate_copilot.work_integration_outbox o
                         WHERE o.department_id=s.department_id AND o.source_id=s.id
                           AND o.status='dead') AS dead_outbound,
                        (SELECT COUNT(*) FROM workmate_copilot.work_integration_outbox o
                         WHERE o.department_id=s.department_id AND o.source_id=s.id
                           AND o.status='pending'
                           AND o.created_at<CURRENT_TIMESTAMP-INTERVAL '60 minutes') AS stale_outbound,
                        (SELECT COUNT(*) FROM workmate_copilot.work_integration_outbox o
                         WHERE o.department_id=s.department_id AND o.source_id=s.id
                           AND o.status='leased' AND o.lease_expires_at<CURRENT_TIMESTAMP) AS expired_lease,
                        (SELECT COUNT(*) FROM workmate_copilot.work_integration_outbox o
                         WHERE o.department_id=s.department_id AND o.source_id=s.id
                           AND o.status='delivered'
                           AND o.delivered_at>=CURRENT_TIMESTAMP-INTERVAL '24 hours') AS outbound_acks_24h,
                        (SELECT COUNT(*) FROM workmate_copilot.work_integration_outbox o
                         WHERE o.department_id=s.department_id AND o.source_id=s.id
                           AND o.status IN ('pending','leased')
                           AND o.created_at<CURRENT_TIMESTAMP-INTERVAL '24 hours') AS overdue_receipts
                      FROM workmate_copilot.work_integration_sources s
                      WHERE s.department_id=%s ORDER BY s.id LIMIT 100
                    """,(dept,))
                    names=[d.name.lower() for d in cur.description]
                    sources=[dict(zip(names,line)) for line in cur.fetchall()]
                    cur.execute("""
                      SELECT id,source_id,issue_code,action,actor_id,created_at
                      FROM workmate_copilot.work_integration_operator_actions
                      WHERE department_id=%s ORDER BY created_at DESC,id DESC LIMIT 20
                    """,(dept,))
                    actions=[{
                        "id":r[0],"source_id":r[1],"issue_code":r[2],
                        "action":r[3],"actor_id":r[4],"created_at":r[5].isoformat(),
                    } for r in cur.fetchall()]
                    cur.execute("COMMIT")
                except Exception:
                    cur.execute("ROLLBACK")
                    raise
        alert_list=[]
        for source in sources:
            source["inbound_key_present"]=bool(configured_secret(source["id"]))
            source["outbound_target_ready"]=bool(
                settings.WORKMATE_OUTBOUND_ENABLED
                and configured_target(source["id"])
            )
            alert_list.extend(_source_alerts(source))
        return {
            "decision":"NO_GO",
            "operational_status":(
                "not_configured" if not sources else
                "needs_attention" if alert_list else
                "configuration_preflight_clear_unverified"
            ),
            "reason":"A real pilot requires independently inspected external release evidence.",
            "window_hours":24,
            "counts":{
                "sources":len(sources),
                "active_sources":sum(1 for s in sources if s["status"]=="active"),
                "inbound_24h":sum(s["inbound_24h"] for s in sources),
                "outbound_acks_24h":sum(s["outbound_acks_24h"] for s in sources),
                "dead_outbound":sum(s["dead_outbound"] for s in sources),
                "open_alerts":len(alert_list),
            },
            "sources":sources,
            "alerts":alert_list,
            "latest_actions":actions,
            "field_verification":"not_automatically_verified",
        }

    @staticmethod
    def record_response(dept,actor,source_id,issue_code,action,note):
        if issue_code not in ALERT_CODES or action not in ("acknowledged","remediation_logged"):
            raise OperationsConflict("Unsupported operational issue or response.")
        if not 16<=len(note.strip())<=1000:
            raise OperationsConflict("A substantive operator note is required.")
        with get_postgres_connection() as conn:
            with conn.cursor() as cur:
                _start(cur,dept)
                try:
                    if not _active_admin(cur,dept,actor):
                        raise OperationsNotFound()
                    cur.execute("""
                      SELECT 1 FROM workmate_copilot.work_integration_sources
                      WHERE id=%s AND department_id=%s
                    """,(source_id,dept))
                    if not cur.fetchone():
                        raise OperationsNotFound()
                    identifier="ops_"+uuid4().hex[:24]
                    cur.execute("""
                      INSERT INTO workmate_copilot.work_integration_operator_actions
                        (id,department_id,source_id,actor_id,issue_code,action,justification)
                      VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING created_at
                    """,(identifier,dept,source_id,actor,issue_code,action,note.strip()))
                    created=cur.fetchone()[0]
                    cur.execute("COMMIT")
                    return {"id":identifier,"source_id":source_id,
                            "issue_code":issue_code,"action":action,
                            "created_at":created.isoformat(),
                            "health_cleared":False}
                except Exception:
                    cur.execute("ROLLBACK")
                    raise
