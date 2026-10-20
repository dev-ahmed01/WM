"""Task-bound exception queue with independent supervisor review.

Every case is opened atomically with a worker block or compiled SOP escalation.
Review means only that a human assessed the incident. A manager cannot use
this service to bypass a hard-stop rule, resume work or certify physical proof.
"""
from __future__ import annotations
from uuid import uuid4
import json
from app.core.database import get_postgres_connection

class CaseNotFound(Exception):
    pass

class CaseConflict(Exception):
    pass


def _begin(cur,department):
    cur.execute("BEGIN")
    cur.execute("SELECT set_config('workmate.department_id',%s,true)",(department,))


def _row(cur):
    if not cur.description:
        return None
    fields=[c.name.lower() for c in cur.description]
    r=cur.fetchone()
    return dict(zip(fields,r)) if r else None


def _rows(cur):
    fields=[c.name.lower() for c in cur.description]
    return [dict(zip(fields,r)) for r in cur.fetchall()]


def _log(cur,case_id,department,actor,action,note):
    cur.execute("""
        INSERT INTO workmate_copilot.work_exception_events
          (id,case_id,department_id,actor_id,action,note)
        VALUES (%s,%s,%s,%s,%s,%s)
    """,(uuid4().hex,case_id,department,actor,action,note[:1000]))


def open_case(cur,work,department,actor,trigger,reason,state_id=None,option=None):
    """Called within WorkExecutionRepository's existing locked transaction."""
    if trigger not in ("worker_report","sop_outcome"):
        raise ValueError("Unsupported incident trigger.")
    if work["status"]!="blocked" or not work.get("execution_session_id"):
        raise ValueError("Only a blocked execution can open an exception case.")
    cur.execute("""
        SELECT id FROM workmate_copilot.work_exceptions
        WHERE work_item_id=%s AND department_id=%s FOR UPDATE
    """,(work["id"],department))
    existing=cur.fetchone()
    if existing:
        raise CaseConflict("This assignment already has a supervisor case.")
    case="case_"+uuid4().hex[:24]
    severity="critical" if trigger=="sop_outcome" else "high"
    cur.execute("""
        INSERT INTO workmate_copilot.work_exceptions
          (id,department_id,work_item_id,execution_session_id,raised_by,
           trigger,severity,reason,state_id,decision_option)
        VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
    """,(case,department,work["id"],work["execution_session_id"],actor,
          trigger,severity,reason[:500],state_id,option))
    _log(cur,case,department,actor,"opened",reason)
    return case


class WorkExceptionRepository:
    @staticmethod
    def list(department,limit=100):
        with get_postgres_connection() as conn:
            with conn.cursor() as cur:
                _begin(cur,department)
                cur.execute("""
                    SELECT c.*,w.title AS work_title,w.status AS work_status,
                           w.assigned_to AS work_assignee,w.workflow_version_id,
                           h.id AS handover_id,h.status AS handover_status,
                           cr.status AS corrective_status
                    FROM workmate_copilot.work_exceptions c
                    JOIN workmate_copilot.work_items w
                      ON w.id=c.work_item_id AND w.department_id=c.department_id
                    LEFT JOIN workmate_copilot.shift_handovers h
                      ON h.work_exception_id=c.id AND h.department_id=c.department_id
                    LEFT JOIN workmate_copilot.work_corrective_requests cr
                      ON cr.case_id=c.id AND cr.department_id=c.department_id
                    WHERE c.department_id=%s
                    ORDER BY
                      CASE WHEN c.status IN ('open','claimed','follow_up_requested')
                                OR cr.status='pending' THEN 0 ELSE 1 END,
                      CASE WHEN c.severity='critical' THEN 0 ELSE 1 END,
                      c.created_at ASC
                    LIMIT %s
                """,(department,limit))
                items=_rows(cur)
                cur.execute("COMMIT")
                return items

    @staticmethod
    def get(department,case_id):
        with get_postgres_connection() as conn:
            with conn.cursor() as cur:
                _begin(cur,department)
                cur.execute("""
                    SELECT c.*,w.title AS work_title,w.status AS work_status,
                           w.assigned_to AS work_assignee,w.workflow_version_id,
                           h.id AS handover_id,h.status AS handover_status,
                           cr.status AS corrective_status
                    FROM workmate_copilot.work_exceptions c
                    JOIN workmate_copilot.work_items w
                      ON w.id=c.work_item_id AND w.department_id=c.department_id
                    LEFT JOIN workmate_copilot.shift_handovers h
                      ON h.work_exception_id=c.id AND h.department_id=c.department_id
                    LEFT JOIN workmate_copilot.work_corrective_requests cr
                      ON cr.case_id=c.id AND cr.department_id=c.department_id
                    WHERE c.id=%s AND c.department_id=%s
                """,(case_id,department))
                case=_row(cur)
                if not case:
                    raise CaseNotFound()
                cur.execute("""
                    SELECT id,actor_id,action,note,event_seq,created_at
                    FROM workmate_copilot.work_exception_events
                    WHERE case_id=%s AND department_id=%s
                    ORDER BY event_seq
                """,(case_id,department))
                case["events"]=_rows(cur)
                # Metadata-only, no raw worker evidence bytes or irrelevant conversations.
                cur.execute("""
                    SELECT id,actor_id,action,event_payload,created_at
                    FROM workmate_copilot.work_item_events
                    WHERE work_item_id=%s AND department_id=%s
                    ORDER BY event_seq LIMIT 150
                """,(case["work_item_id"],department))
                case["work_events"]=_rows(cur)
                cur.execute("""
                  SELECT r.id,r.status,r.proposed_by,r.proposed_at,
                         r.workflow_version_id,r.assigned_to,r.plan_note,
                         r.decided_by,r.decision_note,r.decided_at,r.corrective_work_id,
                         w.title AS procedure_title
                  FROM workmate_copilot.work_corrective_requests r
                  JOIN knowledge_studio.workflow_versions v ON v.id=r.workflow_version_id
                  JOIN knowledge_studio.workflows w ON w.id=v.workflow_id
                  WHERE r.case_id=%s AND r.department_id=%s
                """,(case_id,department))
                case["corrective_request"]=_row(cur)
                cur.execute("COMMIT")
                return case

    @staticmethod
    def claim(department,manager,case_id,expected_revision):
        with get_postgres_connection() as conn:
            with conn.cursor() as cur:
                _begin(cur,department)
                try:
                    cur.execute("""
                        SELECT id,raised_by,reviewer_id,status,revision,work_item_id
                        FROM workmate_copilot.work_exceptions
                        WHERE id=%s AND department_id=%s FOR UPDATE
                    """,(case_id,department))
                    current=_row(cur)
                    if not current:
                        raise CaseNotFound()
                    if (current["raised_by"]==manager or current["status"]!="open"
                        or current["reviewer_id"] is not None or
                        current["revision"]!=expected_revision):
                        raise CaseConflict("This exception is no longer claimable.")
                    cur.execute("""
                        UPDATE workmate_copilot.work_exceptions
                        SET reviewer_id=%s,status='claimed',revision=revision+1,
                            updated_at=CURRENT_TIMESTAMP
                        WHERE id=%s AND department_id=%s
                        RETURNING id,status,revision,reviewer_id,work_item_id
                    """,(manager,case_id,department))
                    updated=_row(cur)
                    _log(cur,case_id,department,manager,"claimed","Review ownership accepted")
                    cur.execute("""
                        INSERT INTO workmate_copilot.work_item_events
                          (id,work_item_id,department_id,actor_id,action,event_payload)
                        VALUES (%s,%s,%s,%s,'exception_claimed',%s::jsonb)
                    """,(uuid4().hex,updated["work_item_id"],department,manager,
                          json.dumps({"case_id":case_id})))
                    cur.execute("COMMIT")
                    return updated
                except Exception:
                    cur.execute("ROLLBACK")
                    raise

    @staticmethod
    def review(department,manager,case_id,revision,decision,note):
        if decision not in ("reviewed","follow_up_requested"):
            raise CaseConflict("Unsupported review decision.")
        if not 8<=len(note.strip())<=1000:
            raise CaseConflict("A meaningful review note is required.")
        with get_postgres_connection() as conn:
            with conn.cursor() as cur:
                _begin(cur,department)
                try:
                    cur.execute("""
                        SELECT id,raised_by,reviewer_id,status,revision,work_item_id
                        FROM workmate_copilot.work_exceptions
                        WHERE id=%s AND department_id=%s FOR UPDATE
                    """,(case_id,department))
                    current=_row(cur)
                    if not current:
                        raise CaseNotFound()
                    if (current["raised_by"]==manager or current["status"] not in ("open","claimed")
                        or current["revision"]!=revision
                        or (current["reviewer_id"] is not None
                            and current["reviewer_id"]!=manager)):
                        raise CaseConflict("Another manager owns or has reviewed this case.")
                    cur.execute("""
                        UPDATE workmate_copilot.work_exceptions
                        SET status=%s,reviewer_id=%s,review_note=%s,
                            reviewed_at=CURRENT_TIMESTAMP,updated_at=CURRENT_TIMESTAMP,
                            revision=revision+1
                        WHERE id=%s AND department_id=%s
                        RETURNING id,status,revision,reviewer_id,work_item_id
                    """,(decision,manager,note.strip(),case_id,department))
                    updated=_row(cur)
                    _log(cur,case_id,department,manager,decision,note.strip())
                    cur.execute("""
                        INSERT INTO workmate_copilot.work_item_events
                          (id,work_item_id,department_id,actor_id,action,event_payload)
                        VALUES (%s,%s,%s,%s,%s,%s::jsonb)
                    """,(uuid4().hex,updated["work_item_id"],department,manager,
                          "exception_reviewed" if decision=="reviewed" else "exception_follow_up",
                          json.dumps({"case_id":case_id,"status":decision})))
                    # Never mutate the work status or paused session here.
                    cur.execute("COMMIT")
                    return updated
                except Exception:
                    cur.execute("ROLLBACK")
                    raise

    @staticmethod
    def action(department,manager,case_id,revision,kind,note):
        """Append a human-authored containment/remediation record, never unblock."""
        if kind not in ("containment_recorded","remediation_proposed"):
            raise CaseConflict("Unsupported containment action.")
        if not 12<=len(note.strip())<=1000:
            raise CaseConflict("An actionable, specific note of 12–1000 characters is required.")
        with get_postgres_connection() as conn:
            with conn.cursor() as cur:
                _begin(cur,department)
                try:
                    cur.execute("""
                        SELECT id,raised_by,reviewer_id,status,revision,work_item_id
                        FROM workmate_copilot.work_exceptions
                        WHERE id=%s AND department_id=%s FOR UPDATE
                    """,(case_id,department))
                    current=_row(cur)
                    if not current:
                        raise CaseNotFound()
                    if (current["raised_by"]==manager
                        or current["reviewer_id"]!=manager
                        or current["status"] not in ("claimed","reviewed","follow_up_requested")
                        or current["revision"]!=revision):
                        raise CaseConflict("Only the assigned supervisor can add a current case action.")
                    cur.execute("""
                        SELECT status FROM workmate_copilot.work_items
                        WHERE id=%s AND department_id=%s FOR UPDATE
                    """,(current["work_item_id"],department))
                    work=cur.fetchone()
                    if not work or work[0]!="blocked":
                        raise CaseConflict("This case is no longer linked to blocked work.")
                    if kind=="remediation_proposed":
                        cur.execute("""
                            SELECT 1 FROM workmate_copilot.work_exception_events
                            WHERE case_id=%s AND department_id=%s
                            AND action='containment_recorded' LIMIT 1
                        """,(case_id,department))
                        if cur.fetchone() is None:
                            raise CaseConflict("Record a containment action before proposing remediation.")
                    cur.execute("""
                        UPDATE workmate_copilot.work_exceptions
                        SET revision=revision+1,updated_at=CURRENT_TIMESTAMP
                        WHERE id=%s AND department_id=%s RETURNING id,revision,status
                    """,(case_id,department))
                    updated=_row(cur)
                    _log(cur,case_id,department,manager,kind,note.strip())
                    cur.execute("""
                        INSERT INTO workmate_copilot.work_item_events
                        (id,work_item_id,department_id,actor_id,action,event_payload)
                        VALUES(%s,%s,%s,%s,%s,%s::jsonb)
                    """,(uuid4().hex,current["work_item_id"],department,manager,kind,
                          json.dumps({"case_id":case_id,"action":kind})))
                    cur.execute("COMMIT")
                    return updated
                except Exception:
                    cur.execute("ROLLBACK")
                    raise

    @staticmethod
    def handover(department,worker,case_id,recipient,next_action,notes):
        """The incident reporter transfers their *actual* paused SOP session.

        Builds a normal shift_handover visible in the existing manager queue.
        The case and handover IDs are not accepted from the client as proof
        of session ownership: ownership and the snapshot come from PostgreSQL.
        """
        if not 2<=len(recipient.strip())<=100 or not 5<=len(next_action.strip())<=1500:
            raise CaseConflict("Recipient and requested action are required.")
        if len(notes)>1500:
            raise CaseConflict("Handover notes exceed the permitted size.")
        with get_postgres_connection() as conn:
            with conn.cursor() as cur:
                _begin(cur,department)
                try:
                    cur.execute("""
                        SELECT c.id,c.work_item_id,c.execution_session_id,c.trigger,
                               c.severity,c.raised_by,w.status AS work_status,
                               s.conversation_id,s.user_id AS session_owner,
                               s.current_state_id,s.status AS session_status,
                               state.title AS state_title
                        FROM workmate_copilot.work_exceptions c
                        JOIN workmate_copilot.work_items w
                          ON w.id=c.work_item_id AND w.department_id=c.department_id
                        JOIN workmate_copilot.workflow_sessions s
                          ON s.id=c.execution_session_id
                        JOIN workmate_copilot.conversations conv
                          ON conv.id=s.conversation_id AND conv.department_id=c.department_id
                             AND conv.user_id=%s
                        LEFT JOIN knowledge_studio.workflow_states state
                          ON state.id=s.current_state_id
                        WHERE c.id=%s AND c.department_id=%s
                        FOR UPDATE OF c,w,s
                    """,(worker,case_id,department))
                    current=_row(cur)
                    if not current:
                        raise CaseNotFound()
                    if (current["raised_by"]!=worker or current["session_owner"]!=worker
                        or current["work_status"]!="blocked" or
                        current["session_status"]!="paused"):
                        raise CaseConflict("Only the original worker can hand over an active blocked case.")
                    cur.execute("""
                        SELECT 1 FROM workmate_copilot.shift_handovers
                        WHERE work_exception_id=%s AND department_id=%s
                    """,(case_id,department))
                    if cur.fetchone():
                        raise CaseConflict("A shift handover already exists for this incident.")
                    handover_id="hov_"+uuid4().hex
                    cur.execute("""
                        INSERT INTO workmate_copilot.shift_handovers (
                          id,department_id,conversation_id,created_by,recipient_label,
                          disposition,exception_type,severity,next_action,notes,
                          snapshot_state,work_exception_id
                        ) VALUES(
                          %s,%s,%s,%s,%s,'blocked_supervisor',%s,%s,%s,%s,
                          jsonb_build_object('workflow_status',%s::text,
                                             'state_id',%s::text,
                                             'step_title',%s::text,
                                             'work_item_id',%s::text,
                                             'case_id',%s::text),
                          %s
                        )
                    """,(handover_id,department,current["conversation_id"],worker,
                          recipient.strip(),
                          "safety_concern" if current["trigger"]=="sop_outcome" else "other",
                          current["severity"],next_action.strip(),notes.strip(),
                          current["session_status"],current["current_state_id"],
                          current["state_title"],current["work_item_id"],case_id,case_id))
                    cur.execute("""
                        INSERT INTO workmate_copilot.shift_handover_events
                          (id,handover_id,department_id,actor_user_id,action)
                        VALUES(%s,%s,%s,%s,'submitted')
                    """,(uuid4().hex,handover_id,department,worker))
                    _log(cur,case_id,department,worker,"handover_linked",
                         "Shift handover submitted for this blocked task.")
                    cur.execute("""
                        INSERT INTO workmate_copilot.work_item_events
                          (id,work_item_id,department_id,actor_id,action,event_payload)
                        VALUES(%s,%s,%s,%s,'handover_linked',%s::jsonb)
                    """,(uuid4().hex,current["work_item_id"],department,worker,
                          json.dumps({"case_id":case_id,"handover_id":handover_id})))
                    cur.execute("COMMIT")
                    return {
                        "handover_id":handover_id,"case_id":case_id,
                        "work_id":current["work_item_id"],"status":"submitted",
                        "work_status":"blocked",
                    }
                except Exception:
                    cur.execute("ROLLBACK")
                    raise
