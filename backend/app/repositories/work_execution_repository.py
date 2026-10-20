"""Atomic execution for real work items using the existing compiled OWD graph.

No new procedure interpreter: compiled workflow_states/steps/transitions/options
remain the authority. Sessions and step executions are the original OWD tables.
Task status, proof and events commit in the SAME PostgreSQL transaction.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import io
import json
import re
from uuid import uuid4

from app.core.database import get_postgres_connection
from app.repositories.owd_repository import OWDRepository
from app.repositories.work_exception_repository import open_case

MAX_EVIDENCE_BYTES = 2 * 1024 * 1024
SAFE_FILE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")


class ExecutionConflict(Exception):
    """Expected stale task, invalid SOP or missing evidence: no changes committed."""


class ExecutionNotFound(Exception):
    """Return the same answer for missing, foreign-department and other-owner work."""


def _fetch(cur):
    names = [c.name.lower() for c in cur.description]
    row = cur.fetchone()
    return dict(zip(names, row)) if row else None


def _records(cur):
    names = [c.name.lower() for c in cur.description]
    return [dict(zip(names, row)) for row in cur.fetchall()]


def _start(cur, dept):
    cur.execute("BEGIN")
    cur.execute("SELECT set_config('workmate.department_id', %s, true)", (dept,))


def _lock_work(cur, dept, actor, task_id, *, manager=False):
    cur.execute("""
      SELECT w.id,w.department_id,w.assigned_to,w.created_by,w.status,
             w.workflow_version_id,w.execution_session_id
      FROM workmate_copilot.work_items w
      WHERE w.id=%s AND w.department_id=%s AND (%s OR w.assigned_to=%s)
      FOR UPDATE OF w
    """, (task_id, dept, manager, actor))
    work = _fetch(cur)
    if not work:
        raise ExecutionNotFound()
    return work


def _event(cur, task, dept, actor, action, detail=None):
    cur.execute("""
      INSERT INTO workmate_copilot.work_item_events
        (id,work_item_id,department_id,actor_id,action,event_payload)
      VALUES (%s,%s,%s,%s,%s,%s::jsonb)
    """, (uuid4().hex, task, dept, actor, action, json.dumps(detail or {})))


def _graph_state(cur, version, state_id):
    cur.execute("""
      SELECT s.id,s.title,s.description,s.state_type,s.is_terminal,s.ordinal_index
      FROM knowledge_studio.workflow_states s
      WHERE s.id=%s AND s.workflow_version_id=%s
    """, (state_id, version))
    state = _fetch(cur)
    if not state:
        raise ExecutionConflict("Bound SOP state is no longer available.")
    return state


def _pending_step(cur, session, state):
    cur.execute("""
      SELECT s.id,s.state_id,s.ordinal_index,s.step_code,s.instruction,
             s.expected_output_type,s.is_mandatory
      FROM knowledge_studio.workflow_steps s
      WHERE s.state_id=%s AND NOT EXISTS (
        SELECT 1 FROM workmate_copilot.workflow_step_executions x
        WHERE x.session_id=%s AND x.step_id=s.id AND x.status='PASSED'
      )
      ORDER BY s.ordinal_index,s.id LIMIT 1
    """, (state, session))
    return _fetch(cur)


def _specs(cur, step_id):
    cur.execute("""
      SELECT id,evidence_type,is_required,min_size_bytes,validation_regex
      FROM knowledge_studio.workflow_evidence_specs WHERE step_id=%s ORDER BY id
    """, (step_id,))
    return _records(cur)


def _options(cur, state):
    cur.execute("""
      SELECT option_code,option_label,target_state_id
      FROM knowledge_studio.workflow_decision_options WHERE state_id=%s
      ORDER BY option_code
    """, (state,))
    return _records(cur)


def _require_published_version(cur, work):
    cur.execute("""
      SELECT 1 FROM knowledge_studio.workflow_versions v
      JOIN knowledge_studio.workflows w ON w.id=v.workflow_id
      WHERE v.id=%s AND v.status='published' AND w.department_id=%s
    """, (work["workflow_version_id"], work["department_id"]))
    if not cur.fetchone():
        raise ExecutionConflict(
            "The linked procedure is no longer published. Stop work and contact your supervisor."
        )


def _guard_rules(cur, state_id):
    # We never pretend that arbitrary SOP safety logic is machine verified.
    cur.execute("""
      SELECT 1 FROM knowledge_studio.workflow_rules
      WHERE state_id=%s AND enforcement_level IN ('HARD_STOP','SUPERVISOR_OVERRIDE','WARNING_CONFIRM')
      LIMIT 1
    """, (state_id,))
    if cur.fetchone():
        raise ExecutionConflict(
            "This SOP state has a mandatory safety/supervisor gate. "
            "Escalate to an authorized supervisor; automated completion is disabled."
        )


def _transition(cur, state_id, option=None):
    cur.execute("""
      SELECT t.id,t.from_state_id,t.to_state_id,t.condition_type,
             t.condition_expression,t.priority, s.title,s.is_terminal,
             o.option_code,o.option_label
      FROM knowledge_studio.workflow_transitions t
      JOIN knowledge_studio.workflow_states s ON s.id=t.to_state_id
      LEFT JOIN knowledge_studio.workflow_decision_options o
        ON o.state_id=t.from_state_id
       AND o.target_state_id=t.to_state_id
       AND UPPER(o.option_code)=UPPER(t.condition_expression)
      WHERE t.from_state_id=%s ORDER BY t.priority,t.id
    """, (state_id,))
    edges = _records(cur)
    # Reuse the same safe deterministic evaluator as Copilot (no eval).
    chosen = OWDRepository._select_transition(
        edges, {"decision_option": option} if option else {}
    )
    if not chosen:
        raise ExecutionConflict(
            "No approved transition matches the supplied decision. Work remains open."
        )
    if chosen["condition_type"] not in ("ALWAYS", "DECISION_OPTION"):
        raise ExecutionConflict(
            "This transition needs a validated rule result or supervisor decision."
        )
    if option is not None and chosen.get('option_code') != option:
        raise ExecutionConflict('The selected option must match its published graph edge.')
    return chosen


def _new_cursor(cur, version, state):
    s = _graph_state(cur, version, state)
    cur.execute("SELECT COUNT(*) FROM knowledge_studio.workflow_steps WHERE state_id=%s",(state,))
    count = cur.fetchone()[0]
    return "completed" if s["is_terminal"] and count == 0 else "active"


def _advance(cur, session, version, state_id, option=None):
    edge = _transition(cur, state_id, option)
    status = _new_cursor(cur, version, edge["to_state_id"])
    cur.execute("""
      UPDATE workmate_copilot.workflow_sessions
      SET previous_state_id=current_state_id,current_state_id=%s,status=%s,
          completed_at=CASE WHEN %s='completed' THEN CURRENT_TIMESTAMP ELSE completed_at END,
          updated_at=CURRENT_TIMESTAMP
      WHERE id=%s AND status='active'
    """, (edge["to_state_id"], status, status, session))
    if cur.rowcount != 1:
        raise ExecutionConflict("Session changed while recording this step.")
    return status


def _position(cur, work):
    session_id = work["execution_session_id"]
    if not session_id:
        return {"work_id":work["id"],"status":work["status"],
                "workflow_version_id":work["workflow_version_id"],"session_id":None,
                "state":None,"step":None,"decision_options":[],"decision_question":None,
                "safety_gates":[],"completed_steps":0,"total_steps":0}
    cur.execute("""
      SELECT current_state_id,status FROM workmate_copilot.workflow_sessions
      WHERE id=%s
    """, (session_id,))
    active = _fetch(cur)
    if not active:
        raise ExecutionConflict("Linked execution session is unavailable.")
    state = _graph_state(cur, work["workflow_version_id"], active["current_state_id"])
    cur.execute("""
      SELECT rule_code,enforcement_level,error_message
      FROM knowledge_studio.workflow_rules
      WHERE state_id=%s AND enforcement_level IN
        ('HARD_STOP','SUPERVISOR_OVERRIDE','WARNING_CONFIRM')
      ORDER BY id
    """,(state["id"],))
    gates=_records(cur)
    step = _pending_step(cur, session_id, state["id"])
    if step:
        step["evidence_specs"] = _specs(cur, step["id"])
    cur.execute("""
      SELECT COUNT(*) FROM knowledge_studio.workflow_steps s
      JOIN knowledge_studio.workflow_states st ON s.state_id=st.id
      WHERE st.workflow_version_id=%s
    """, (work["workflow_version_id"],))
    total = cur.fetchone()[0]
    cur.execute("""
      SELECT COUNT(*) FROM workmate_copilot.workflow_step_executions
      WHERE session_id=%s AND status='PASSED'
    """, (session_id,))
    done = cur.fetchone()[0]
    choices=_options(cur,state["id"]) if not step else []
    question=None
    if choices:
        cur.execute("""
            SELECT question FROM knowledge_studio.workflow_decisions
            WHERE state_id=%s ORDER BY id LIMIT 1
        """,(state["id"],))
        answer=cur.fetchone()
        question=answer[0] if answer else None
    return {"work_id":work["id"],"status":work["status"],
            "workflow_version_id":work["workflow_version_id"],
            "session_id":session_id,"state":state,"step":step,
            "decision_options":choices,"decision_question":question,
            "safety_gates":gates,
            "completed_steps":done,"total_steps":total}


def _decode_evidence(file, spec):
    filename = file["filename"]
    if not SAFE_FILE.fullmatch(filename) or ".." in filename:
        raise ExecutionConflict("Unsafe attachment filename.")
    encoded = file["content_base64"]
    if len(encoded) > ((MAX_EVIDENCE_BYTES + 2) // 3 * 4) + 16:
        raise ExecutionConflict("Evidence exceeds 2 MB.")
    try:
        raw = base64.b64decode(encoded, validate=True)
    except (ValueError,binascii.Error) as exc:
        raise ExecutionConflict("Evidence bytes are not valid base64.") from exc
    if not raw or len(raw) > MAX_EVIDENCE_BYTES:
        raise ExecutionConflict("Evidence must contain no more than 2 MB.")
    if spec.get("min_size_bytes") and len(raw) < int(spec["min_size_bytes"]):
        raise ExecutionConflict("Evidence does not meet the published minimum size.")
    if spec.get("validation_regex"):
        raise ExecutionConflict("This evidence requires a published validation rule not yet supported.")
    typ = spec["evidence_type"]
    if typ == "DOCUMENT_PDF":
        if not (raw.startswith(b"%PDF-") and filename.lower().endswith(".pdf")):
            raise ExecutionConflict("The required document must be a valid PDF.")
        try:
            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(raw), strict=True)
            if reader.is_encrypted or len(reader.pages) < 1:
                raise ValueError("No readable pages")
        except Exception as exc:
            raise ExecutionConflict("The attached PDF is corrupt or unreadable.") from exc
    elif typ == "PHOTO_JPEG":
        if not (raw.startswith(b"\xff\xd8\xff") and filename.lower().endswith((".jpg",".jpeg"))):
            raise ExecutionConflict("The required image must be JPEG.")
        try:
            from PIL import Image
            with Image.open(io.BytesIO(raw)) as img:
                if img.format != "JPEG" or img.width < 1 or img.height < 1:
                    raise ValueError("Invalid JPEG")
                img.verify()
        except Exception as exc:
            raise ExecutionConflict("The attached JPEG is corrupt or unreadable.") from exc
    else:
        raise ExecutionConflict("This evidence type requires specialist human verification.")
    digest = hashlib.sha256(raw).hexdigest()
    return raw, digest


class WorkExecutionRepository:
    @staticmethod
    def procedures(department):
        with get_postgres_connection() as conn:
            with conn.cursor() as cur:
                _start(cur,department)
                cur.execute("""
                  SELECT v.id AS workflow_version_id,w.title,w.workflow_code,
                         v.version_number
                  FROM knowledge_studio.workflow_versions v
                  JOIN knowledge_studio.workflows w ON w.id=v.workflow_id
                  WHERE w.department_id=%s AND v.status='published'
                    AND EXISTS (SELECT 1 FROM knowledge_studio.workflow_states s
                                WHERE s.workflow_version_id=v.id AND s.is_initial)
                  ORDER BY w.title,v.version_number DESC LIMIT 100
                """, (department,))
                items = _records(cur)
                cur.execute("COMMIT")
                return items

    @staticmethod
    def bind(department,manager,work_id,version_id):
        with get_postgres_connection() as conn:
            with conn.cursor() as cur:
                _start(cur,department)
                try:
                    work = _lock_work(cur,department,manager,work_id,manager=True)
                    if work["status"]!="queued":
                        raise ExecutionConflict("Only a queued work item may be bound.")
                    cur.execute("""
                      SELECT v.id,w.title,v.version_number FROM knowledge_studio.workflow_versions v
                      JOIN knowledge_studio.workflows w ON w.id=v.workflow_id
                      WHERE v.id=%s AND v.status='published' AND w.department_id=%s
                      AND EXISTS (SELECT 1 FROM knowledge_studio.workflow_states s
                                  WHERE s.workflow_version_id=v.id AND s.is_initial)
                    """, (version_id,department))
                    published = cur.fetchone()
                    if not published:
                        raise ExecutionConflict("Only a published SOP in this department may be assigned.")
                    cur.execute("""
                      UPDATE workmate_copilot.work_items SET workflow_version_id=%s,
                        status='ready',updated_at=CURRENT_TIMESTAMP WHERE id=%s
                    """,(version_id,work_id))
                    _event(cur,work_id,department,manager,"bound",
                           {"workflow_version_id":version_id,"version_number":published[2]})
                    cur.execute("COMMIT")
                    return {"work_id":work_id,"status":"ready","workflow_version_id":version_id}
                except Exception:
                    cur.execute("ROLLBACK")
                    raise

    @staticmethod
    def start(department,actor,work_id):
        with get_postgres_connection() as conn:
            with conn.cursor() as cur:
                _start(cur,department)
                try:
                    work=_lock_work(cur,department,actor,work_id)
                    if work["status"]!="ready":
                        raise ExecutionConflict("This assignment is not ready for execution.")
                    version=work["workflow_version_id"]
                    cur.execute("""
                      SELECT s.id FROM knowledge_studio.workflow_states s
                      JOIN knowledge_studio.workflow_versions v ON v.id=s.workflow_version_id
                      JOIN knowledge_studio.workflows w ON w.id=v.workflow_id
                      WHERE v.id=%s AND v.status='published' AND w.department_id=%s
                        AND s.is_initial
                      ORDER BY s.ordinal_index LIMIT 1
                    """,(version,department))
                    initial=cur.fetchone()
                    if not initial:
                        raise ExecutionConflict("The published SOP has no starting state.")
                    conv_id="conv_w_"+uuid4().hex[:24]
                    session="sess_w_"+uuid4().hex[:24]
                    cur.execute("""
                      INSERT INTO workmate_copilot.conversations(id,user_id,department_id)
                      VALUES (%s,%s,%s)
                    """,(conv_id,actor,department))
                    cur.execute("""
                      INSERT INTO workmate_copilot.workflow_sessions
                        (id,conversation_id,workflow_version_id,current_state_id,
                         user_id,status,session_context)
                      VALUES (%s,%s,%s,%s,%s,'active','{}'::jsonb)
                    """,(session,conv_id,version,initial[0],actor))
                    cur.execute("""
                      UPDATE workmate_copilot.work_items SET execution_session_id=%s,
                        status='active',updated_at=CURRENT_TIMESTAMP WHERE id=%s
                    """,(session,work_id))
                    _event(cur,work_id,department,actor,"started",
                           {"session_id":session,"workflow_version_id":version})
                    work["status"]="active";work["execution_session_id"]=session
                    view=_position(cur,work)
                    cur.execute("COMMIT")
                    return view
                except Exception:
                    cur.execute("ROLLBACK")
                    raise

    @staticmethod
    def position(department,actor,manager,work_id):
        with get_postgres_connection() as conn:
            with conn.cursor() as cur:
                _start(cur,department)
                try:
                    work=_lock_work(cur,department,actor,work_id,manager=manager)
                    view=_position(cur,work)
                    cur.execute("COMMIT")
                    return view
                except Exception:
                    cur.execute("ROLLBACK")
                    raise

    @staticmethod
    def progress(department,actor,work_id,expected_step,confirmation,text,number,evidence):
        with get_postgres_connection() as conn:
            with conn.cursor() as cur:
                _start(cur,department)
                try:
                    work=_lock_work(cur,department,actor,work_id)
                    if work["status"]!="active":
                        raise ExecutionConflict("Only active work can record a step.")
                    session=work["execution_session_id"]
                    cur.execute("""
                      SELECT id,current_state_id FROM workmate_copilot.workflow_sessions
                      WHERE id=%s AND user_id=%s AND status='active' FOR UPDATE
                    """,(session,actor))
                    current=_fetch(cur)
                    if not current:
                        raise ExecutionConflict("Active work session was not found.")
                    _require_published_version(cur,work)
                    state=_graph_state(cur,work["workflow_version_id"],current["current_state_id"])
                    _guard_rules(cur,state["id"])
                    step=_pending_step(cur,session,state["id"])
                    if not step or step["id"]!=expected_step:
                        raise ExecutionConflict("This step is out of date. Refresh the work item.")
                    output=step["expected_output_type"]
                    if output=="CONFIRMATION" and confirmation is not True:
                        raise ExecutionConflict("Explicit worker confirmation is required.")
                    if output in ("TEXT_INPUT","SINGLE_CHOICE","MULTI_CHOICE") and len(text.strip())<2:
                        raise ExecutionConflict("Provide the required work observation.")
                    if output=="NUMERIC_INPUT" and number is None:
                        raise ExecutionConflict("A numeric reading is required.")
                    if output=="DOCUMENT_UPLOAD" and not evidence:
                        raise ExecutionConflict("A document or photo is required.")
                    specs=_specs(cur,step["id"])
                    required={sp["id"]:sp for sp in specs if sp["is_required"]}
                    provided={}
                    if len(evidence)>4:
                        raise ExecutionConflict("Too many evidence attachments.")
                    for file in evidence:
                        spec=next((s for s in specs if s["id"]==file["spec_id"]),None)
                        if not spec or file["spec_id"] in provided:
                            raise ExecutionConflict("Attachment is not required for this SOP step.")
                        provided[file["spec_id"]]=(_decode_evidence(file,spec),file,spec)
                    if set(required)-set(provided):
                        raise ExecutionConflict("All mandatory SOP evidence must be attached.")
                    if output=="DOCUMENT_UPLOAD" and not provided:
                        raise ExecutionConflict("A compatible document is required.")
                    execution="exec_w_"+uuid4().hex[:24]
                    cur.execute("""
                      INSERT INTO workmate_copilot.workflow_step_executions
                        (id,session_id,step_id,status,input_payload)
                      VALUES (%s,%s,%s,'PASSED',%s::jsonb)
                    """,(execution,session,step["id"],json.dumps({
                        "source":"workmate_task_ui","worker_attested":confirmation,
                        "observation":text[:1500],"numeric_reading":number,
                        "attachments":len(provided),"independently_verified":False
                    })))
                    attachment_meta=[]
                    for spec_id,(decoded,file,spec) in provided.items():
                        raw,digest=decoded
                        object_id=uuid4().hex
                        cur.execute("""
                          INSERT INTO shared.source_objects
                            (id,department_id,filename,sha256_hash,content)
                          VALUES (%s,%s,%s,%s,%s)
                        """,(object_id,department,file["filename"],digest,raw))
                        cur.execute("""
                          INSERT INTO workmate_copilot.workflow_evidence_submissions
                            (id,step_execution_id,evidence_spec_id,stage_file_uri,
                             verification_status)
                          VALUES (%s,%s,%s,%s,'RECEIVED_UNVERIFIED')
                        """,(uuid4().hex,execution,spec_id,"pgobj:"+object_id))
                        attachment_meta.append({"spec_id":spec_id,"sha256":digest,
                                                "bytes":len(raw),"verified":False})
                    pending=_pending_step(cur,session,state["id"])
                    status="active"
                    if pending is None:
                        if state["is_terminal"]:
                            cur.execute("""
                              UPDATE workmate_copilot.workflow_sessions
                              SET status='completed',completed_at=CURRENT_TIMESTAMP,
                                updated_at=CURRENT_TIMESTAMP WHERE id=%s AND status='active'
                            """,(session,))
                            status="completed"
                        else:
                            status=_advance(cur,session,work["workflow_version_id"],state["id"])
                    if status=="completed":
                        cur.execute("""
                          UPDATE workmate_copilot.work_items
                          SET status='completed',completed_at=CURRENT_TIMESTAMP,
                            updated_at=CURRENT_TIMESTAMP WHERE id=%s
                        """,(work_id,))
                        work["status"]="completed"
                    _event(cur,work_id,department,actor,"step_recorded",{
                        "step_id":step["id"],"execution_id":execution,"evidence":attachment_meta,
                        "independently_verified":False
                    })
                    if status=="completed":
                        _event(cur,work_id,department,actor,"completed",{"session_id":session})
                    view=_position(cur,work)
                    cur.execute("COMMIT")
                    return view
                except Exception:
                    cur.execute("ROLLBACK")
                    raise

    @staticmethod
    def decide(department,actor,work_id,option):
        with get_postgres_connection() as conn:
            with conn.cursor() as cur:
                _start(cur,department)
                try:
                    work=_lock_work(cur,department,actor,work_id)
                    if work["status"]!="active":
                        raise ExecutionConflict("Only active work can advance.")
                    cur.execute("""
                      SELECT current_state_id FROM workmate_copilot.workflow_sessions
                      WHERE id=%s AND status='active' AND user_id=%s FOR UPDATE
                    """,(work["execution_session_id"],actor))
                    record=_fetch(cur)
                    if not record:
                        raise ExecutionConflict("Active session not available.")
                    _require_published_version(cur,work)
                    state=_graph_state(cur,work["workflow_version_id"],record["current_state_id"])
                    _guard_rules(cur,state["id"])
                    if _pending_step(cur,work["execution_session_id"],state["id"]):
                        raise ExecutionConflict("Complete the current step first.")
                    options=_options(cur,state["id"])
                    if not options or option not in {o["option_code"] for o in options}:
                        raise ExecutionConflict("Choose a published decision option.")
                    status=_advance(cur,work["execution_session_id"],
                                    work["workflow_version_id"],state["id"],option)
                    if status=="completed":
                        cur.execute("""
                          UPDATE workmate_copilot.work_items
                          SET status='completed',completed_at=CURRENT_TIMESTAMP,
                            updated_at=CURRENT_TIMESTAMP WHERE id=%s
                        """,(work_id,))
                        work["status"]="completed"
                    _event(cur,work_id,department,actor,"decision_recorded",{
                        "from_state_id":state["id"],"option_code":option
                    })
                    # A published escalation outcome must open a supervisor
                    # case, not leave the task in misleading "active" status.
                    if status=="active":
                        cur.execute("""
                            SELECT current_state_id FROM workmate_copilot.workflow_sessions
                            WHERE id=%s
                        """,(work["execution_session_id"],))
                        escalated=_graph_state(cur,work["workflow_version_id"],cur.fetchone()[0])
                        if escalated["state_type"]=="ESCALATION":
                            cur.execute("""
                                UPDATE workmate_copilot.workflow_sessions
                                SET status='paused',updated_at=CURRENT_TIMESTAMP
                                WHERE id=%s AND status='active'
                            """,(work["execution_session_id"],))
                            if cur.rowcount!=1:
                                raise ExecutionConflict("Unable to secure escalated session.")
                            cur.execute("""
                                UPDATE workmate_copilot.work_items
                                SET status='blocked',updated_at=CURRENT_TIMESTAMP WHERE id=%s
                            """,(work_id,))
                            work["status"]="blocked"
                            case_id=open_case(
                                cur,work,department,actor,"sop_outcome",
                                "Published SOP outcome requires supervisor review.",
                                escalated["id"],option,
                            )
                            _event(cur,work_id,department,actor,"blocked",{
                                "reason":"Published SOP escalation","case_id":case_id,
                                "state_id":escalated["id"],
                            })
                    if status=="completed":
                        _event(cur,work_id,department,actor,"completed",
                               {"session_id":work["execution_session_id"]})
                    view=_position(cur,work)
                    cur.execute("COMMIT")
                    return view
                except Exception:
                    cur.execute("ROLLBACK")
                    raise

    @staticmethod
    def continue_state(department,actor,work_id):
        """Explicit progression through a published state with zero steps/decisions."""
        with get_postgres_connection() as conn:
            with conn.cursor() as cur:
                _start(cur,department)
                try:
                    work=_lock_work(cur,department,actor,work_id)
                    if work["status"]!="active":
                        raise ExecutionConflict("Only active work may continue.")
                    _require_published_version(cur,work)
                    cur.execute("""
                      SELECT current_state_id FROM workmate_copilot.workflow_sessions
                      WHERE id=%s AND status='active' AND user_id=%s FOR UPDATE
                    """,(work["execution_session_id"],actor))
                    sess=_fetch(cur)
                    if not sess:
                        raise ExecutionConflict("Active workflow session not available.")
                    state=_graph_state(cur,work["workflow_version_id"],sess["current_state_id"])
                    _guard_rules(cur,state["id"])
                    if _pending_step(cur,work["execution_session_id"],state["id"]):
                        raise ExecutionConflict("Complete the mandatory step first.")
                    if _options(cur,state["id"]):
                        raise ExecutionConflict("Choose an approved decision path first.")
                    if state["is_terminal"]:
                        cur.execute("""
                          UPDATE workmate_copilot.workflow_sessions
                          SET status='completed',completed_at=CURRENT_TIMESTAMP,
                              updated_at=CURRENT_TIMESTAMP
                          WHERE id=%s AND status='active'
                        """,(work["execution_session_id"],))
                        status="completed"
                    else:
                        status=_advance(cur,work["execution_session_id"],
                                        work["workflow_version_id"],state["id"])
                    if status=="completed":
                        cur.execute("""
                          UPDATE workmate_copilot.work_items
                          SET status='completed',completed_at=CURRENT_TIMESTAMP,
                              updated_at=CURRENT_TIMESTAMP WHERE id=%s
                        """,(work_id,))
                        work["status"]="completed"
                    _event(cur,work_id,department,actor,"state_advanced",{"state_id":state["id"]})
                    if status=="completed":
                        _event(cur,work_id,department,actor,"completed",
                               {"session_id":work["execution_session_id"]})
                    position=_position(cur,work)
                    cur.execute("COMMIT")
                    return position
                except Exception:
                    cur.execute("ROLLBACK")
                    raise

    @staticmethod
    def change_status(department,actor,work_id,operation,reason=""):
        with get_postgres_connection() as conn:
            with conn.cursor() as cur:
                _start(cur,department)
                try:
                    work=_lock_work(cur,department,actor,work_id)
                    old=work["status"]
                    allowed={"pause":("active","paused","paused"),
                             "resume":("paused","active","resumed"),
                             "block":("active","blocked","blocked")}
                    expected,new,event=allowed[operation]
                    if old!=expected:
                        raise ExecutionConflict("This work item is not in a state that allows "+operation+".")
                    cur.execute("""
                      UPDATE workmate_copilot.workflow_sessions SET status=%s,
                        updated_at=CURRENT_TIMESTAMP WHERE id=%s AND user_id=%s
                    """,("paused" if new=="blocked" else new,
                         work["execution_session_id"],actor))
                    if cur.rowcount!=1:
                        raise ExecutionConflict("Unable to update bound session.")
                    cur.execute("""
                      UPDATE workmate_copilot.work_items SET status=%s,
                        updated_at=CURRENT_TIMESTAMP WHERE id=%s
                    """,(new,work_id))
                    _event(cur,work_id,department,actor,event,{"reason":reason[:500]})
                    work["status"]=new
                    if new=="blocked":
                        case_id=open_case(
                            cur,work,department,actor,"worker_report",reason,
                        )
                        _event(cur,work_id,department,actor,"blocked",{
                            "reason":reason[:500],"case_id":case_id,
                            "source":"supervisor_exception",
                        })
                    view=_position(cur,work)
                    cur.execute("COMMIT")
                    return view
                except Exception:
                    cur.execute("ROLLBACK")
                    raise

    @staticmethod
    def timeline(department,actor,manager,work_id):
        with get_postgres_connection() as conn:
            with conn.cursor() as cur:
                _start(cur,department)
                try:
                    _lock_work(cur,department,actor,work_id,manager=manager)
                    cur.execute("""
                      SELECT id,actor_id,action,event_payload,created_at
                      FROM workmate_copilot.work_item_events
                      WHERE work_item_id=%s AND department_id=%s
                      ORDER BY event_seq LIMIT 200
                    """,(work_id,department))
                    events=_records(cur)
                    for event in events:
                        event["created_at"]=event["created_at"].isoformat()
                    cur.execute("COMMIT")
                    return events
                except Exception:
                    cur.execute("ROLLBACK")
                    raise
