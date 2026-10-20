"""Two-person authorization of a NEW corrective task for a blocked incident.

An approved request issues a fresh evidence-gated work item bound to a
published SOP. It NEVER resumes or clears the original blocked session,
changes original evidence, or certifies the physical hazard as resolved.
"""
from uuid import uuid4
import json
from app.core.database import get_postgres_connection
from app.repositories.work_exception_repository import (
    CaseNotFound,CaseConflict,_begin,_row,_log,
)


def _approved_version(cur,department,version_id):
    cur.execute("""
       SELECT v.id,w.title,v.version_number
       FROM knowledge_studio.workflow_versions v
       JOIN knowledge_studio.workflows w ON w.id=v.workflow_id
       WHERE v.id=%s AND w.department_id=%s AND v.status='published'
       AND EXISTS (
          SELECT 1 FROM knowledge_studio.workflow_states s
          JOIN knowledge_studio.workflow_steps step ON step.state_id=s.id
          WHERE s.workflow_version_id=v.id AND s.is_initial
             AND s.state_type='ATOMIC_STEP')
       AND EXISTS (
          SELECT 1 FROM knowledge_studio.workflow_states s
          WHERE s.workflow_version_id=v.id AND s.is_terminal
             AND s.state_type='END')
    """,(version_id,department))
    return cur.fetchone()


def _active_employee(cur,department,actor):
    cur.execute("""
      SELECT 1 FROM security.users u
      JOIN security.user_roles ur ON ur.user_id=u.id
      JOIN security.roles r ON r.id=ur.role_id
      WHERE u.id=%s AND u.department_id=%s AND u.status='active'
       AND LOWER(r.name)='employee'
    """,(actor,department))
    return cur.fetchone() is not None


def _case_locked(cur,department,case_id):
    cur.execute("""
       SELECT c.id,c.raised_by,c.reviewer_id,c.status,c.revision,
              c.work_item_id,c.execution_session_id,
              w.title,w.work_type,w.status AS work_status,
              s.status AS session_status
       FROM workmate_copilot.work_exceptions c
       JOIN workmate_copilot.work_items w
        ON w.id=c.work_item_id AND w.department_id=c.department_id
       JOIN workmate_copilot.workflow_sessions s
        ON s.id=c.execution_session_id
       WHERE c.id=%s AND c.department_id=%s
       FOR UPDATE OF c,w,s
    """,(case_id,department))
    return _row(cur)


def _valid_hold(case):
    return case["work_status"]=="blocked" and case["session_status"]=="paused"


def _event(cur,work_id,dept,actor,action,payload):
    cur.execute("""
      INSERT INTO workmate_copilot.work_item_events
       (id,work_item_id,department_id,actor_id,action,event_payload)
      VALUES(%s,%s,%s,%s,%s,%s::jsonb)
    """,(uuid4().hex,work_id,dept,actor,action,json.dumps(payload)))


class CorrectiveWorkRepository:
    @staticmethod
    def request(department,manager,case_id,revision,version_id,assignee,plan_note):
        if not 20<=len(plan_note.strip())<=1000:
            raise CaseConflict("Describe the exact corrective controls and verification work.")
        with get_postgres_connection() as conn:
            with conn.cursor() as cur:
                _begin(cur,department)
                try:
                    case=_case_locked(cur,department,case_id)
                    if not case:
                        raise CaseNotFound()
                    if (case["revision"]!=revision or case["reviewer_id"]!=manager
                        or case["raised_by"]==manager
                        or case["status"] not in ("reviewed","follow_up_requested")
                        or not _valid_hold(case)):
                        raise CaseConflict("A currently reviewed, still-blocked case is required.")
                    cur.execute("""
                      SELECT action FROM workmate_copilot.work_exception_events
                      WHERE case_id=%s AND department_id=%s
                        AND action IN ('containment_recorded','remediation_proposed')
                      GROUP BY action
                    """,(case_id,department))
                    events={row[0] for row in cur.fetchall()}
                    if events!={"containment_recorded","remediation_proposed"}:
                        raise CaseConflict("Containment and documented remediation must precede corrective work.")
                    if not _approved_version(cur,department,version_id):
                        raise CaseConflict("Corrective work needs a published, executable SOP in this department.")
                    if not _active_employee(cur,department,assignee):
                        raise CaseConflict("Choose an active worker in this department.")
                    identifier="cwr_"+uuid4().hex[:24]
                    cur.execute("""
                      INSERT INTO workmate_copilot.work_corrective_requests
                       (id,department_id,case_id,proposed_by,workflow_version_id,
                        assigned_to,plan_note)
                      VALUES(%s,%s,%s,%s,%s,%s,%s)
                      RETURNING id,status,proposed_by,workflow_version_id,assigned_to
                    """,(identifier,department,case_id,manager,version_id,assignee,plan_note.strip()))
                    request=_row(cur)
                    _log(cur,case_id,department,manager,"corrective_requested",
                         "New task proposed under an independent approved-SOP check.")
                    _event(cur,case["work_item_id"],department,manager,"corrective_requested",
                           {"request_id":identifier,"workflow_version_id":version_id})
                    cur.execute("""
                      UPDATE workmate_copilot.work_exceptions
                      SET revision=revision+1,updated_at=CURRENT_TIMESTAMP
                      WHERE id=%s AND department_id=%s
                    """,(case_id,department))
                    cur.execute("COMMIT")
                    return request
                except Exception:
                    cur.execute("ROLLBACK")
                    raise

    @staticmethod
    def decide(department,admin,case_id,request_id,decision,decision_note):
        if decision not in ("approved","rejected"):
            raise CaseConflict("Only approve or reject is supported.")
        if not 16<=len(decision_note.strip())<=1000:
            raise CaseConflict("A documented independent decision is required.")
        with get_postgres_connection() as conn:
            with conn.cursor() as cur:
                _begin(cur,department)
                try:
                    case=_case_locked(cur,department,case_id)
                    if not case:
                        raise CaseNotFound()
                    cur.execute("""
                       SELECT id,proposed_by,workflow_version_id,assigned_to,plan_note,status
                       FROM workmate_copilot.work_corrective_requests
                       WHERE id=%s AND case_id=%s AND department_id=%s
                       FOR UPDATE
                    """,(request_id,case_id,department))
                    request=_row(cur)
                    if not request:
                        raise CaseNotFound()
                    if (request["status"]!="pending" or not _valid_hold(case)
                        or case["status"] not in ("reviewed","follow_up_requested")
                        or admin in (request["proposed_by"],case["reviewer_id"],
                                     case["raised_by"],request["assigned_to"])):
                        raise CaseConflict("A separate authorized administrator must approve a pending held case.")
                    work_id=None
                    if decision=="approved":
                        if not _approved_version(cur,department,request["workflow_version_id"]):
                            raise CaseConflict("The proposed SOP is no longer published and executable.")
                        if not _active_employee(cur,department,request["assigned_to"]):
                            raise CaseConflict("The corrective worker is no longer eligible.")
                        work_id="wrk_"+uuid4().hex
                        cur.execute("""
                          INSERT INTO workmate_copilot.work_items
                            (id,department_id,created_by,assigned_to,title,work_type,priority,
                             instructions,status,workflow_version_id,external_reference)
                          VALUES(%s,%s,%s,%s,%s,%s,'high',%s,'ready',%s,%s)
                        """,(work_id,department,admin,request["assigned_to"],
                              ("Corrective verification — "+case["title"])[:180],
                              case["work_type"],
                              ("Corrective task for case "+case_id+". "+request["plan_note"])[:1200],
                              request["workflow_version_id"],case_id))
                        _event(cur,work_id,department,admin,"created",
                               {"source_case_id":case_id,"request_id":request_id})
                        _event(cur,work_id,department,admin,"bound",
                               {"source_case_id":case_id,
                                "workflow_version_id":request["workflow_version_id"]})
                    cur.execute("""
                       UPDATE workmate_copilot.work_corrective_requests
                       SET status=%s,decided_by=%s,decision_note=%s,
                           decided_at=CURRENT_TIMESTAMP,corrective_work_id=%s
                       WHERE id=%s AND case_id=%s AND department_id=%s
                       RETURNING id,status,decided_by,corrective_work_id,workflow_version_id
                    """,(decision,admin,decision_note.strip(),work_id,request_id,case_id,department))
                    updated=_row(cur)
                    action="corrective_approved" if decision=="approved" else "corrective_rejected"
                    _log(cur,case_id,department,admin,action,decision_note.strip())
                    _event(cur,case["work_item_id"],department,admin,action,
                           {"request_id":request_id,"corrective_work_id":work_id})
                    cur.execute("""
                      UPDATE workmate_copilot.work_exceptions
                      SET revision=revision+1,updated_at=CURRENT_TIMESTAMP
                      WHERE id=%s AND department_id=%s
                    """,(case_id,department))
                    # The original task/session are never updated or unpaused.
                    cur.execute("COMMIT")
                    return updated
                except Exception:
                    cur.execute("ROLLBACK")
                    raise
