"""Phase 6A — idempotent WMS/ERP work intake, explicitly staged for review.

This is an authenticated *adapter contract*, not a claim of live SAP/Oracle/Odoo
connectivity. Never import executable sessions or trust source-declared approval.
All source fields are normalized and server-owned department/actor are required.
"""
from __future__ import annotations

import hashlib
import json
from uuid import uuid4

from app.core.database import get_postgres_connection


class IntegrationNotFound(Exception):
    pass


class IntegrationConflict(Exception):
    pass


def _scope(cur, department):
    cur.execute("BEGIN")
    cur.execute("SELECT set_config('workmate.department_id',%s,true)", (department,))


def _record(cur):
    if not cur.description:
        return None
    row=cur.fetchone()
    return dict(zip((x.name.lower() for x in cur.description),row)) if row else None


def _readable(entry):
    if not entry:
        return None
    for key in ("created_at","decided_at"):
        if entry.get(key) is not None:
            entry[key]=entry[key].isoformat()
    return entry


def _columns():
    return ("id,department_id,source_system,external_event_id,external_work_id,"
            "payload_digest,normalized_payload,submitted_by,status,decided_by,"
            "decision_note,decided_at,work_item_id,created_at")


def _active_manager(cur,dept,actor):
    cur.execute("""
      SELECT 1 FROM security.users u
      JOIN security.user_roles ur ON ur.user_id=u.id
      JOIN security.roles r ON r.id=ur.role_id
      WHERE u.id=%s AND u.department_id=%s AND u.status='active'
        AND LOWER(r.name) IN ('admin','manager')
    """, (actor,dept))
    return cur.fetchone() is not None


def _active_employee(cur,dept,actor):
    cur.execute("""
      SELECT 1 FROM security.users u
      JOIN security.user_roles ur ON ur.user_id=u.id
      JOIN security.roles r ON r.id=ur.role_id
      WHERE u.id=%s AND u.department_id=%s AND u.status='active'
        AND LOWER(r.name)='employee'
    """,(actor,dept))
    return cur.fetchone() is not None


def _canonical(payload):
    # Source identity and versioned normalized task fields, not HTTP headers or
    # user claims. Stable bytes make retries deterministic.
    return json.dumps(payload,ensure_ascii=False,sort_keys=True,separators=(",",":"))


class IntegrationIntakeRepository:
    @staticmethod
    def stage(department,actor,payload):
        if payload["source_system"] not in {"sap","oracle","odoo","custom_wms"}:
            raise IntegrationConflict("Unsupported connector schema.")
        digest=hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()
        with get_postgres_connection() as conn:
            with conn.cursor() as cur:
                _scope(cur,department)
                try:
                    if not _active_manager(cur,department,actor):
                        raise IntegrationConflict("Only active department managers may stage work.")
                    identifier="int_"+uuid4().hex[:24]
                    cur.execute("""
                      INSERT INTO workmate_copilot.work_integration_intake
                        (id,department_id,source_system,external_event_id,external_work_id,
                         payload_digest,normalized_payload,submitted_by)
                      VALUES(%s,%s,%s,%s,%s,%s,%s::jsonb,%s)
                      ON CONFLICT DO NOTHING RETURNING """+_columns(),(
                        identifier,department,payload["source_system"],payload["external_event_id"],
                        payload["external_work_id"],digest,_canonical(payload),actor,
                    ))
                    created=_record(cur)
                    if created:
                        cur.execute("COMMIT")
                        return {**_readable(created),"replayed":False}
                    # Resolve both unique constraints. Retrying the SAME event with
                    # the SAME normalized bytes is safe, even after acceptance.
                    cur.execute("""
                      SELECT """+_columns()+"""
                      FROM workmate_copilot.work_integration_intake
                      WHERE department_id=%s AND source_system=%s
                        AND (external_event_id=%s OR external_work_id=%s)
                      FOR UPDATE
                    """,(department,payload["source_system"],payload["external_event_id"],
                         payload["external_work_id"]))
                    existing=_record(cur)
                    if (existing and existing["external_event_id"]==payload["external_event_id"]
                        and existing["external_work_id"]==payload["external_work_id"]
                        and existing["payload_digest"]==digest
                        and existing["normalized_payload"]==payload):
                        cur.execute("COMMIT")
                        return {**_readable(existing),"replayed":True}
                    raise IntegrationConflict(
                        "Source event or business work ID was already submitted with different content."
                    )
                except Exception:
                    cur.execute("ROLLBACK")
                    raise

    @staticmethod
    def list(department,actor,limit=100):
        with get_postgres_connection() as conn:
            with conn.cursor() as cur:
                _scope(cur,department)
                try:
                    if not _active_manager(cur,department,actor):
                        raise IntegrationNotFound()
                    cur.execute("""
                      SELECT """+_columns()+"""
                      FROM workmate_copilot.work_integration_intake
                      WHERE department_id=%s
                      ORDER BY CASE WHEN status='pending' THEN 0 ELSE 1 END, created_at DESC
                      LIMIT %s
                    """,(department,limit))
                    labels=[c.name.lower() for c in cur.description]
                    entries=[_readable(dict(zip(labels,row))) for row in cur.fetchall()]
                    cur.execute("COMMIT")
                    return entries
                except Exception:
                    cur.execute("ROLLBACK")
                    raise

    @staticmethod
    def decide(department,actor,intake_id,decision,decision_note):
        if decision not in ("accepted","rejected") or not 16<=len(decision_note.strip())<=1000:
            raise IntegrationConflict("An explicit acceptance or rejection with a substantive note is required.")
        with get_postgres_connection() as conn:
            with conn.cursor() as cur:
                _scope(cur,department)
                try:
                    if not _active_manager(cur,department,actor):
                        raise IntegrationNotFound()
                    cur.execute("""
                      SELECT """+_columns()+"""
                      FROM workmate_copilot.work_integration_intake
                      WHERE id=%s AND department_id=%s FOR UPDATE
                    """,(intake_id,department))
                    intake=_record(cur)
                    if not intake:
                        raise IntegrationNotFound()
                    if intake["status"]!="pending" or intake["submitted_by"]==actor:
                        raise IntegrationConflict(
                            "A separate reviewer must decide a pending integration record once."
                        )
                    new_work=None
                    if decision=="accepted":
                        payload=intake["normalized_payload"]
                        assignee=payload["assigned_to"]
                        if assignee and not _active_employee(cur,department,assignee):
                            raise IntegrationConflict(
                                "External assignee is not an active worker in this department."
                            )
                        new_work="wrk_"+uuid4().hex
                        external_ref=f'{intake["source_system"].upper()}:{intake["external_work_id"]}'
                        cur.execute("""
                          INSERT INTO workmate_copilot.work_items(
                            id,department_id,created_by,assigned_to,external_reference,
                            title,work_type,priority,instructions,status
                          ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,'queued')
                        """,(new_work,department,actor,assignee,external_ref,
                             payload["title"],payload["work_type"],payload["priority"],
                             payload["instructions"]))
                        cur.execute("""
                          INSERT INTO workmate_copilot.work_item_events
                            (id,work_item_id,department_id,actor_id,action,event_payload)
                          VALUES (%s,%s,%s,%s,'integration_imported',%s::jsonb)
                        """,(uuid4().hex,new_work,department,actor,
                             json.dumps({"intake_id":intake_id,
                                         "source_system":intake["source_system"],
                                         "external_event_id":intake["external_event_id"],
                                         "source_payload_digest":intake["payload_digest"],
                                         "reviewer_id":actor})))
                    cur.execute("""
                      UPDATE workmate_copilot.work_integration_intake
                      SET status=%s,decided_by=%s,decision_note=%s,
                          decided_at=CURRENT_TIMESTAMP,work_item_id=%s
                      WHERE id=%s AND department_id=%s AND status='pending'
                      RETURNING """+_columns(),(
                        decision,actor,decision_note.strip(),new_work,intake_id,department,
                    ))
                    updated=_record(cur)
                    if not updated:
                        raise IntegrationConflict("Integration record changed before review.")
                    # No workflow version is assigned or session created here.
                    cur.execute("COMMIT")
                    return _readable(updated)
                except Exception:
                    cur.execute("ROLLBACK")
                    raise
