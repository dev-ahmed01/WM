"""Phase 4D: separately reviewed corrective evidence and independent site attestation.

An operator's completed corrective SOP is necessary, not sufficient, for case
closure. This records named human assertions but never certifies physical
conditions, unpauses the original session, or resumes blocked work.
"""
from __future__ import annotations

import json
from uuid import uuid4

from app.core.database import get_postgres_connection
from app.repositories.work_exception_repository import (
    CaseConflict, CaseNotFound, _begin, _row, _rows, _log,
)
from app.repositories.work_corrective_repository import _case_locked, _event, _valid_hold


class CaseClosureRepository:
    @staticmethod
    def review_evidence(department, supervisor, case_id, revision, note):
        if not 20 <= len(note.strip()) <= 1000:
            raise CaseConflict("A substantive corrective evidence review is required.")
        with get_postgres_connection() as conn:
            with conn.cursor() as cur:
                _begin(cur, department)
                try:
                    case = _case_locked(cur, department, case_id)
                    if not case:
                        raise CaseNotFound()
                    if (
                        case["revision"] != revision
                        or case["status"] not in ("reviewed", "follow_up_requested")
                        or not _valid_hold(case)
                        or case["reviewer_id"] != supervisor
                        or supervisor == case["raised_by"]
                    ):
                        raise CaseConflict("Only the current case reviewer may review completed corrective proof.")
                    cur.execute("""
                      SELECT r.id AS request_id,r.proposed_by,r.decided_by,r.assigned_to,
                             r.corrective_work_id,r.workflow_version_id,
                             w.status AS corrective_status,w.execution_session_id AS corrective_session_id,
                             w.workflow_version_id AS work_version,w.completed_at,
                             s.status AS session_status,s.completed_at AS session_completed_at
                      FROM workmate_copilot.work_corrective_requests r
                      JOIN workmate_copilot.work_items w
                        ON w.id=r.corrective_work_id AND w.department_id=r.department_id
                      JOIN workmate_copilot.workflow_sessions s
                        ON s.id=w.execution_session_id AND s.user_id=r.assigned_to
                           AND s.workflow_version_id=r.workflow_version_id
                      WHERE r.case_id=%s AND r.department_id=%s AND r.status='approved'
                      FOR UPDATE OF r,w,s
                    """, (case_id, department))
                    corrective = _row(cur)
                    if not corrective:
                        raise CaseConflict("An independently approved corrective task is required.")
                    if (corrective["corrective_status"] != "completed"
                        or corrective["session_status"] != "completed"
                        or not corrective["completed_at"]
                        or not corrective["session_completed_at"]
                        or corrective["work_version"] != corrective["workflow_version_id"]):
                        raise CaseConflict("Finish the actual corrective SOP before reviewing evidence.")
                    cur.execute("""
                      SELECT 1 FROM workmate_copilot.work_case_closures
                      WHERE case_id=%s AND department_id=%s
                    """, (case_id, department))
                    if cur.fetchone():
                        raise CaseConflict("Corrective evidence has already been reviewed.")
                    cur.execute("""
                      SELECT COUNT(*) FROM workmate_copilot.workflow_step_executions
                      WHERE session_id=%s AND status='PASSED'
                    """, (corrective["corrective_session_id"],))
                    step_count = cur.fetchone()[0]
                    if step_count < 1:
                        raise CaseConflict("Corrective SOP needs at least one recorded checkpoint.")
                    # Raw documents remain private. Store only immutable submission IDs,
                    # source checksum, spec ID and received/unverified status.
                    cur.execute("""
                      SELECT evidence.id, evidence.evidence_spec_id,
                             evidence.verification_status, obj.sha256_hash,
                             octet_length(obj.content) AS file_bytes
                      FROM workmate_copilot.workflow_step_executions step
                      JOIN workmate_copilot.workflow_evidence_submissions evidence
                        ON evidence.step_execution_id=step.id
                      JOIN shared.source_objects obj
                        ON evidence.stage_file_uri='pgobj:'||obj.id
                           AND obj.department_id=%s
                      WHERE step.session_id=%s AND step.status='PASSED'
                        AND evidence.verification_status='RECEIVED_UNVERIFIED'
                      ORDER BY evidence.id
                    """, (department, corrective["corrective_session_id"]))
                    files = _rows(cur)
                    if not files:
                        raise CaseConflict("Attach received corrective SOP evidence before review.")
                    snapshot = {
                        "source": "completed_corrective_sop",
                        "recorded_step_count": step_count,
                        "received_evidence": [
                            {"submission_id": f["id"], "spec_id": f["evidence_spec_id"],
                             "sha256": f["sha256_hash"], "bytes": f["file_bytes"],
                             "verification": "received_unverified"}
                            for f in files
                        ],
                        "physical_inspection_verified_by_system": False,
                    }
                    identifier = "cls_" + uuid4().hex[:24]
                    cur.execute("""
                      INSERT INTO workmate_copilot.work_case_closures
                        (id,department_id,case_id,corrective_request_id,corrective_work_id,
                         corrective_session_id,evidence_snapshot,evidence_reviewed_by,
                         evidence_review_note)
                      VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s)
                      RETURNING id,case_id,corrective_work_id,evidence_snapshot,
                                evidence_reviewed_by,evidence_reviewed_at
                    """, (identifier, department, case_id, corrective["request_id"],
                          corrective["corrective_work_id"], corrective["corrective_session_id"],
                          json.dumps(snapshot), supervisor, note.strip()))
                    recorded = _row(cur)
                    cur.execute("""
                      UPDATE workmate_copilot.work_exceptions
                      SET revision=revision+1,updated_at=CURRENT_TIMESTAMP
                      WHERE id=%s AND department_id=%s
                    """, (case_id, department))
                    _log(cur, case_id, department, supervisor, "evidence_reviewed", note.strip())
                    _event(cur, case["work_item_id"], department, supervisor,
                           "evidence_reviewed", {"case_id": case_id,
                                                 "closure_id": identifier,
                                                 "corrective_work_id": corrective["corrective_work_id"]})
                    cur.execute("COMMIT")
                    return recorded
                except Exception:
                    cur.execute("ROLLBACK")
                    raise

    @staticmethod
    def accept_site(department, admin, case_id, revision, site_reference, note, attested):
        if attested is not True:
            raise CaseConflict("Explicit independent site attestation is required.")
        if not 8 <= len(site_reference.strip()) <= 128:
            raise CaseConflict("A real site inspection reference is required.")
        if not 30 <= len(note.strip()) <= 1000:
            raise CaseConflict("Record specific on-site inspection findings and remaining controls.")
        with get_postgres_connection() as conn:
            with conn.cursor() as cur:
                _begin(cur, department)
                try:
                    case = _case_locked(cur, department, case_id)
                    if not case:
                        raise CaseNotFound()
                    if (case["revision"] != revision
                        or case["status"] not in ("reviewed", "follow_up_requested")
                        or not _valid_hold(case)):
                        raise CaseConflict("Only a current, still-blocked reviewed case can be closed.")
                    cur.execute("""
                      SELECT c.*,r.proposed_by,r.decided_by,r.assigned_to,r.status AS corrective_status,
                             w.status AS work_status,s.status AS session_status
                      FROM workmate_copilot.work_case_closures c
                      JOIN workmate_copilot.work_corrective_requests r
                        ON r.id=c.corrective_request_id AND r.case_id=c.case_id
                           AND r.department_id=c.department_id
                      JOIN workmate_copilot.work_items w
                        ON w.id=c.corrective_work_id AND w.department_id=c.department_id
                      JOIN workmate_copilot.workflow_sessions s
                        ON s.id=c.corrective_session_id AND s.id=w.execution_session_id
                      WHERE c.case_id=%s AND c.department_id=%s FOR UPDATE OF c,r,w,s
                    """, (case_id, department))
                    record = _row(cur)
                    if not record:
                        raise CaseConflict("A different supervisor must first review corrective evidence.")
                    if (record["site_accepted_at"] is not None
                        or record["corrective_status"] != "approved"
                        or record["work_status"] != "completed"
                        or record["session_status"] != "completed"):
                        raise CaseConflict("Corrective evidence review is stale or the case is already closed.")
                    excluded = (
                        case["raised_by"], case["reviewer_id"],
                        record["proposed_by"], record["decided_by"],
                        record["assigned_to"], record["evidence_reviewed_by"],
                    )
                    if admin in excluded:
                        raise CaseConflict("Site acceptance requires a separate authorized administrator.")
                    cur.execute("""
                      SELECT 1 FROM security.users u
                      JOIN security.user_roles ur ON ur.user_id=u.id
                      JOIN security.roles role ON role.id=ur.role_id
                      WHERE u.id=%s AND u.department_id=%s AND u.status='active'
                        AND LOWER(role.name)='admin'
                    """, (admin, department))
                    if not cur.fetchone():
                        raise CaseConflict("An active department administrator must sign site acceptance.")
                    evidence = record["evidence_snapshot"].get("received_evidence", [])
                    if not evidence:
                        raise CaseConflict("No reviewed corrective evidence was retained.")
                    # Ensure recorded evidence still exists and its checksums match
                    # the signed review snapshot; do not inspect images automatically.
                    cur.execute("""
                      SELECT ev.id,obj.sha256_hash
                      FROM workmate_copilot.workflow_step_executions step
                      JOIN workmate_copilot.workflow_evidence_submissions ev
                        ON ev.step_execution_id=step.id
                      JOIN shared.source_objects obj
                        ON ev.stage_file_uri='pgobj:'||obj.id AND obj.department_id=%s
                      WHERE step.session_id=%s AND step.status='PASSED'
                        AND ev.verification_status='RECEIVED_UNVERIFIED'
                      ORDER BY ev.id
                    """, (department,record["corrective_session_id"]))
                    actual = {ident: digest for ident,digest in cur.fetchall()}
                    if actual != {f["submission_id"]:f["sha256"] for f in evidence}:
                        raise CaseConflict("Corrective evidence changed after review; do not close the case.")
                    cur.execute("""
                      UPDATE workmate_copilot.work_case_closures
                      SET site_accepted_by=%s,site_record_reference=%s,
                          site_acceptance_note=%s,site_accepted_at=CURRENT_TIMESTAMP
                      WHERE id=%s AND site_accepted_at IS NULL
                      RETURNING id,site_accepted_by,site_record_reference,site_accepted_at
                    """, (admin,site_reference.strip(),note.strip(),record["id"]))
                    accepted = _row(cur)
                    if not accepted:
                        raise CaseConflict("The site acceptance was already recorded.")
                    cur.execute("""
                      UPDATE workmate_copilot.work_exceptions
                      SET status='closed',closed_at=CURRENT_TIMESTAMP,
                          revision=revision+1,updated_at=CURRENT_TIMESTAMP
                      WHERE id=%s AND department_id=%s AND revision=%s
                        AND status IN ('reviewed','follow_up_requested')
                      RETURNING id,status,revision,closed_at
                    """, (case_id, department,revision))
                    closed = _row(cur)
                    if not closed:
                        raise CaseConflict("The case revision changed during site acceptance.")
                    _log(cur,case_id,department,admin,"site_accepted",site_reference.strip())
                    _log(cur,case_id,department,admin,"case_closed",note.strip())
                    _event(cur,case["work_item_id"],department,admin,"case_closed",
                           {"case_id":case_id,"closure_id":record["id"],
                            "site_reference":site_reference.strip(),
                            "original_work_still_blocked":True})
                    # NO UPDATE to original blocked work, paused session or evidence.
                    cur.execute("COMMIT")
                    return {**closed,**accepted,"original_work_status":"blocked"}
                except Exception:
                    cur.execute("ROLLBACK")
                    raise
