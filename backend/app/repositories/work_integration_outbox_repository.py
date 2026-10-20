"""Phase 6C: only reviewed signed source work enters a durable ERP ACK outbox.

No external ACK is trusted as permission to change a WorkMate task, SOP, or
exception. The delivery worker leases individual events, outside the inbox
transaction, and records bounded metadata only.
"""
from __future__ import annotations

import json
from uuid import uuid4
from app.core.database import get_postgres_connection

class OutboxConflict(Exception):
    pass

class OutboxNotFound(Exception):
    pass

def _row(cur):
    row=cur.fetchone()
    return dict(zip((x.name.lower() for x in cur.description),row)) if row else None

def _scope(cur,dept):
    cur.execute("BEGIN")
    cur.execute("SELECT set_config('workmate.department_id',%s,true)",(dept,))

def _admin(cur,dept,actor):
    cur.execute("""
      SELECT 1 FROM security.users u
      JOIN security.user_roles ur ON ur.user_id=u.id
      JOIN security.roles r ON r.id=ur.role_id
      WHERE u.id=%s AND u.department_id=%s AND u.status='active'
        AND lower(r.name)='admin'
    """,(actor,dept))
    return cur.fetchone() is not None

def _readable(item):
    if not item:
        return item
    for key in ("created_at","updated_at","delivered_at","next_attempt_at","lease_expires_at"):
        if item.get(key) is not None:
            item[key]=item[key].isoformat()
    return item

def enqueue_reviewed_work(cur,department,intake,work_id):
    """Call INSIDE human acceptance transaction, after queued work was inserted.

    Manual entries are NOT assumed to have ERP destinations. Only a signed,
    staged source delivery links a connector to the approved inbox entry.
    """
    cur.execute("""
      SELECT d.source_id
      FROM workmate_copilot.work_integration_deliveries d
      JOIN workmate_copilot.work_integration_sources s
        ON s.id=d.source_id AND s.department_id=d.department_id
      WHERE d.intake_id=%s AND d.department_id=%s
        AND d.status IN ('staged','replayed')
      ORDER BY d.received_at ASC,d.id ASC LIMIT 1
    """,(intake["id"],department))
    signed=cur.fetchone()
    if not signed:
        return None
    out_id="out_"+uuid4().hex[:24]
    payload={
        "event_id":out_id,"event_type":"work_accepted",
        "source_system":intake["source_system"],
        "external_event_id":intake["external_event_id"],
        "external_work_id":intake["external_work_id"],
        "work_item_id":work_id,"work_status":"queued",
    }
    cur.execute("""
      INSERT INTO workmate_copilot.work_integration_outbox
        (id,department_id,source_id,intake_id,work_item_id,payload)
      VALUES(%s,%s,%s,%s,%s,%s::jsonb)
      ON CONFLICT (intake_id,event_type) DO NOTHING
      RETURNING id
    """,(out_id,department,signed[0],intake["id"],work_id,
         json.dumps(payload,sort_keys=True,separators=(",",":"))))
    created=cur.fetchone()
    if not created:
        raise OutboxConflict("Reviewed order already has an outbound reconciliation event.")
    return out_id

class OutboxRepository:
    @staticmethod
    def claim(limit=10):
        """Worker-only process: atomic SKIP LOCKED lease, globally unique token.

        Never hold a DB transaction during HTTP. Stale leases are reclaimed.
        """
        if not 1<=limit<=25:
            raise ValueError("Invalid claim limit")
        claims=[]
        with get_postgres_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("BEGIN")
                try:
                    # A worker can die after taking its FINAL lease. Expire
                    # exhausted jobs into human-recoverable dead-letter state;
                    # otherwise they would remain leased forever.
                    cur.execute("""
                      SELECT id,department_id,attempts
                      FROM workmate_copilot.work_integration_outbox
                      WHERE status='leased' AND attempts>=5
                        AND lease_expires_at<CURRENT_TIMESTAMP
                      FOR UPDATE SKIP LOCKED LIMIT %s
                    """,(limit,))
                    expired=cur.fetchall()
                    for expired_id,expired_dept,attempt_no in expired:
                        cur.execute("""
                          INSERT INTO workmate_copilot.work_integration_outbox_attempts
                            (id,department_id,outbox_id,attempt_number,result,code)
                          SELECT %s,%s,%s,%s,'dead','lease_expired'
                          WHERE NOT EXISTS(
                            SELECT 1 FROM workmate_copilot.work_integration_outbox_attempts
                            WHERE outbox_id=%s AND attempt_number=%s)
                        """,(uuid4().hex,expired_dept,expired_id,attempt_no,
                             expired_id,attempt_no))
                        cur.execute("""
                          UPDATE workmate_copilot.work_integration_outbox
                          SET status='dead',lease_token=NULL,lease_expires_at=NULL,
                              last_error_code='lease_expired',updated_at=CURRENT_TIMESTAMP
                          WHERE id=%s
                        """,(expired_id,))
                    cur.execute("""
                      SELECT o.id,o.source_id,o.department_id,o.payload,o.attempts
                      FROM workmate_copilot.work_integration_outbox o
                      JOIN workmate_copilot.work_integration_sources s
                        ON s.id=o.source_id AND s.department_id=o.department_id
                      WHERE s.status='active'
                        AND o.attempts<5
                        AND ((o.status='pending' AND o.next_attempt_at<=CURRENT_TIMESTAMP)
                             OR (o.status='leased' AND o.lease_expires_at<CURRENT_TIMESTAMP))
                      ORDER BY o.next_attempt_at ASC,o.created_at ASC
                      FOR UPDATE OF o SKIP LOCKED LIMIT %s
                    """,(limit,))
                    records=[dict(zip((x.name.lower() for x in cur.description),line))
                             for line in cur.fetchall()]
                    for task in records:
                        # Retries after worker crash preserve the same event id.
                        if task["attempts"]>0:
                            cur.execute("""
                              INSERT INTO workmate_copilot.work_integration_outbox_attempts
                                (id,department_id,outbox_id,attempt_number,result,code)
                              SELECT %s,%s,%s,%s,'retry','lease_expired'
                              WHERE NOT EXISTS (
                                SELECT 1 FROM workmate_copilot.work_integration_outbox_attempts
                                WHERE outbox_id=%s AND attempt_number=%s)
                            """,(uuid4().hex,task["department_id"],task["id"],
                                 task["attempts"],task["id"],task["attempts"]))
                        token=uuid4().hex
                        cur.execute("""
                          UPDATE workmate_copilot.work_integration_outbox
                          SET status='leased',attempts=attempts+1,lease_token=%s,
                              lease_expires_at=CURRENT_TIMESTAMP+INTERVAL '60 seconds',
                              updated_at=CURRENT_TIMESTAMP
                          WHERE id=%s
                        """,(token,task["id"]))
                        claims.append({**task,"lease_token":token,
                                       "attempt":task["attempts"]+1})
                    cur.execute("COMMIT")
                    return claims
                except Exception:
                    cur.execute("ROLLBACK")
                    raise

    @staticmethod
    def settle(event_id,token,delivered,receipt=None,reason="none"):
        """Exactly the current valid lease may settle. Receipts never mutate work."""
        if reason not in ("none","not_configured","transport_error","http_status",
                          "invalid_ack","lease_expired","unsafe_target"):
            raise ValueError("Invalid delivery outcome")
        if delivered and (not receipt or len(receipt)>100):
            raise ValueError("Valid remote receipt required")
        with get_postgres_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("BEGIN")
                try:
                    cur.execute("""
                      SELECT id,department_id,attempts FROM workmate_copilot.work_integration_outbox
                      WHERE id=%s AND lease_token=%s AND status='leased'
                        AND lease_expires_at>=CURRENT_TIMESTAMP FOR UPDATE
                    """,(event_id,token))
                    row=_row(cur)
                    if not row:
                        cur.execute("ROLLBACK")
                        return False
                    if delivered:
                        status="delivered"
                        next_delay=0
                        code="none"
                    else:
                        status="dead" if row["attempts"]>=5 else "pending"
                        next_delay={1:30,2:120,3:300,4:900}.get(row["attempts"],900)
                        code=reason
                    cur.execute("""
                      UPDATE workmate_copilot.work_integration_outbox
                      SET status=%s,lease_token=NULL,lease_expires_at=NULL,
                          next_attempt_at=CURRENT_TIMESTAMP+(%s*INTERVAL '1 second'),
                          ack_reference=%s,delivered_at=CASE WHEN %s THEN CURRENT_TIMESTAMP ELSE NULL END,
                          last_error_code=%s,updated_at=CURRENT_TIMESTAMP
                      WHERE id=%s
                    """,(status,next_delay,receipt if delivered else None,delivered,code,event_id))
                    cur.execute("""
                      INSERT INTO workmate_copilot.work_integration_outbox_attempts
                        (id,department_id,outbox_id,attempt_number,result,code)
                      VALUES (%s,%s,%s,%s,%s,%s)
                    """,(uuid4().hex,row["department_id"],event_id,row["attempts"],
                         "delivered" if delivered else ("dead" if status=="dead" else "retry"),code))
                    cur.execute("COMMIT")
                    return True
                except Exception:
                    cur.execute("ROLLBACK")
                    raise

    @staticmethod
    def list(dept,admin,source_id,limit=50):
        with get_postgres_connection() as conn:
            with conn.cursor() as cur:
                _scope(cur,dept)
                try:
                    if not _admin(cur,dept,admin):
                        raise OutboxNotFound()
                    cur.execute("""
                      SELECT 1 FROM workmate_copilot.work_integration_sources
                      WHERE id=%s AND department_id=%s
                    """,(source_id,dept))
                    if not cur.fetchone():
                        raise OutboxNotFound()
                    cur.execute("""
                      SELECT id,intake_id,work_item_id,event_type,status,attempts,
                             recovered_count,next_attempt_at,last_error_code,ack_reference,
                             created_at,updated_at,delivered_at
                      FROM workmate_copilot.work_integration_outbox
                      WHERE source_id=%s AND department_id=%s
                      ORDER BY created_at DESC LIMIT %s
                    """,(source_id,dept,limit))
                    keys=[x.name.lower() for x in cur.description]
                    rows=[_readable(dict(zip(keys,row))) for row in cur.fetchall()]
                    cur.execute("COMMIT")
                    return rows
                except Exception:
                    cur.execute("ROLLBACK")
                    raise

    @staticmethod
    def recover(dept,admin,out_id,note):
        if not 16<=len(note.strip())<=1000:
            raise OutboxConflict("A substantive recovery justification is required.")
        with get_postgres_connection() as conn:
            with conn.cursor() as cur:
                _scope(cur,dept)
                try:
                    if not _admin(cur,dept,admin):
                        raise OutboxNotFound()
                    cur.execute("""
                      SELECT o.id,o.status,o.recovered_count,s.status AS source_status
                      FROM workmate_copilot.work_integration_outbox o
                      JOIN workmate_copilot.work_integration_sources s
                        ON s.id=o.source_id AND s.department_id=o.department_id
                      WHERE o.id=%s AND o.department_id=%s FOR UPDATE OF o
                    """,(out_id,dept))
                    row=_row(cur)
                    if not row:
                        raise OutboxNotFound()
                    if (row["status"]!="dead" or row["recovered_count"]>=3
                        or row["source_status"]!="active"):
                        raise OutboxConflict("Only dead deliveries to active sources can be recovered, at most three times.")
                    cur.execute("""
                      UPDATE workmate_copilot.work_integration_outbox
                      SET status='pending',attempts=0,recovered_count=recovered_count+1,
                          next_attempt_at=CURRENT_TIMESTAMP,updated_at=CURRENT_TIMESTAMP,
                          last_error_code='manually_recovered'
                      WHERE id=%s
                    """,(out_id,))
                    cur.execute("""
                      INSERT INTO workmate_copilot.work_integration_outbox_recoveries
                        (id,department_id,outbox_id,actor_id,justification)
                      VALUES(%s,%s,%s,%s,%s)
                    """,(uuid4().hex,dept,out_id,admin,note.strip()))
                    cur.execute("COMMIT")
                    return {"id":out_id,"status":"pending",
                            "recovered_count":row["recovered_count"]+1}
                except Exception:
                    cur.execute("ROLLBACK")
                    raise
