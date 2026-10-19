"""Role-scoped persisted shift handovers with atomic review events.

The trusted department comes from authenticated identity, never a request field.
Review changes *handover* status only; it must never advance workflow steps.
"""
from __future__ import annotations

import uuid
from typing import Any

from app.core.database import get_postgres_connection


class HandoverRepository:
    COLUMNS = (
        "id,department_id,conversation_id,created_by,recipient_label,"
        "disposition,exception_type,severity,next_action,notes,"
        "snapshot_state,status,reviewed_by,reviewed_at,review_note,created_at,updated_at"
    )

    @staticmethod
    def _record(cur) -> dict[str, Any] | None:
        row = cur.fetchone()
        if not row:
            return None
        keys = [col.name.lower() for col in cur.description]
        record = dict(zip(keys, row))
        for key in ("created_at", "updated_at", "reviewed_at"):
            if record.get(key):
                record[key] = record[key].isoformat()
        return record

    @staticmethod
    def submit(department: str, user: str, conversation: str, recipient: str,
               disposition: str, exception_type: str, severity: str, next_action: str,
               notes: str) -> dict | None:
        handover_id = "hov_" + uuid.uuid4().hex
        with get_postgres_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("BEGIN")
                try:
                    cur.execute("SELECT set_config('workmate.department_id',%s,true)", (department,))
                    # Fetch *only* conversations owned by this actor. No client-submitted
                    # session state is trusted. The latest actual workflow state is captured.
                    cur.execute("""
                        SELECT c.id,
                          ws.status, ws.current_state_id, st.title
                        FROM workmate_copilot.conversations c
                        LEFT JOIN LATERAL (
                           SELECT status,current_state_id FROM workmate_copilot.workflow_sessions
                           WHERE conversation_id=c.id AND user_id=%s
                           ORDER BY started_at DESC LIMIT 1
                        ) ws ON true
                        LEFT JOIN knowledge_studio.workflow_states st ON st.id=ws.current_state_id
                        WHERE c.id=%s AND c.user_id=%s AND c.department_id=%s
                        FOR UPDATE OF c
                    """, (user, conversation, user, department))
                    snapshot = cur.fetchone()
                    if not snapshot:
                        cur.execute("ROLLBACK")
                        return None
                    cur.execute("""
                        INSERT INTO workmate_copilot.shift_handovers (
                            id,department_id,conversation_id,created_by,recipient_label,
                            disposition,exception_type,severity,next_action,notes,snapshot_state
                        ) VALUES (
                            %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                            jsonb_build_object('workflow_status',%s::text,
                                               'state_id',%s::text,
                                               'step_title',%s::text)
                        ) RETURNING """ + HandoverRepository.COLUMNS,
                        (handover_id, department, conversation, user, recipient,
                         disposition, exception_type, severity, next_action, notes,
                         snapshot[1], snapshot[2], snapshot[3]))
                    record = HandoverRepository._record(cur)
                    cur.execute("""
                        INSERT INTO workmate_copilot.shift_handover_events
                        (id,handover_id,department_id,actor_user_id,action)
                        VALUES (%s,%s,%s,%s,'submitted')
                    """, (uuid.uuid4().hex, handover_id, department, user))
                    cur.execute("COMMIT")
                    return record
                except Exception:
                    cur.execute("ROLLBACK")
                    raise

    @staticmethod
    def list(department: str, user: str, reviewer: bool, limit: int = 40) -> list[dict]:
        with get_postgres_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("BEGIN")
                try:
                    cur.execute("SELECT set_config('workmate.department_id',%s,true)", (department,))
                    cur.execute("""
                        SELECT """ + HandoverRepository.COLUMNS + """
                        FROM workmate_copilot.shift_handovers
                        WHERE department_id=%s AND (%s OR created_by=%s)
                        ORDER BY created_at DESC LIMIT %s
                    """, (department, reviewer, user, limit))
                    columns = [c.name.lower() for c in cur.description]
                    items = [dict(zip(columns, row)) for row in cur.fetchall()]
                    for record in items:
                        for key in ("created_at", "updated_at", "reviewed_at"):
                            if record.get(key):
                                record[key] = record[key].isoformat()
                    cur.execute("COMMIT")
                    return items
                except Exception:
                    cur.execute("ROLLBACK")
                    raise

    @staticmethod
    def review(department: str, reviewer: str, handover_id: str,
               decision: str, note: str) -> dict | None:
        with get_postgres_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("BEGIN")
                try:
                    cur.execute("SELECT set_config('workmate.department_id',%s,true)", (department,))
                    # One conditional update prevents repeated / conflicting review.
                    # A person cannot acknowledge their own handover.
                    cur.execute("""
                        UPDATE workmate_copilot.shift_handovers
                        SET status=%s,reviewed_by=%s,reviewed_at=CURRENT_TIMESTAMP,
                            review_note=%s,updated_at=CURRENT_TIMESTAMP
                        WHERE id=%s AND department_id=%s AND status='submitted'
                          AND created_by<>%s
                        RETURNING """ + HandoverRepository.COLUMNS,
                        (decision, reviewer, note, handover_id, department, reviewer))
                    updated = HandoverRepository._record(cur)
                    if not updated:
                        cur.execute("ROLLBACK")
                        return None
                    cur.execute("""
                        INSERT INTO workmate_copilot.shift_handover_events
                        (id,handover_id,department_id,actor_user_id,action)
                        VALUES (%s,%s,%s,%s,%s)
                    """, (uuid.uuid4().hex,handover_id,department,reviewer,decision))
                    cur.execute("COMMIT")
                    return updated
                except Exception:
                    cur.execute("ROLLBACK")
                    raise
