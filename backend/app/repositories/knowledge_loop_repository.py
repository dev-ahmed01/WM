"""Knowledge gaps and manager approval of reviewed SOP drafts.

Scoping: admins act on their organization, managers on their own department;
the scope is resolved from the database by the API layer and passed in. An
out-of-scope id behaves exactly like a missing one.
"""
from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

from app.core.database import get_postgres_connection
from app.repositories.procedure_draft_repository import COLUMNS, DraftConflict, DraftNotFound, _dict, _event, _start

GAP_COLS = ("g.id, g.department_id, g.reported_by, g.question, g.occurrences, g.status, g.employee_reply, "
            "g.replied_by, g.replied_at, g.draft_id, g.escalation_id, g.created_at, g.updated_at, g.resolved_at")
GAP_FROM = "FROM knowledge_studio.knowledge_gaps g JOIN security.departments d ON d.id = g.department_id"


class GapNotFound(Exception):
    pass


def _iso(row: Dict[str, Any]) -> Dict[str, Any]:
    for k in ("replied_at", "created_at", "updated_at", "resolved_at"):
        if row.get(k) is not None:
            row[k] = row[k].isoformat()
    return row


def _gap_dicts(cur) -> List[Dict[str, Any]]:
    names = [c.name for c in cur.description]
    return [_iso(dict(zip(names, r))) for r in cur.fetchall()]


class KnowledgeGapRepository:
    @staticmethod
    def record(department: str, user_id: str, message_id: str, question: str) -> tuple[str, bool]:
        """Create the gap, or count a repeat of a still-open identical question. Returns (id, is_new)."""
        gap_id = f"gap_{uuid.uuid4().hex[:16]}"
        text = " ".join(question.split())[:1000]
        with get_postgres_connection() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO knowledge_studio.knowledge_gaps (id, department_id, reported_by, conversation_message_id, question) "
                "VALUES (%s,%s,%s,%s,%s) "
                "ON CONFLICT (department_id, lower(question)) WHERE status IN ('open','answered','drafting') "
                "DO UPDATE SET occurrences = knowledge_studio.knowledge_gaps.occurrences + 1, updated_at = now() "
                "RETURNING id, (xmax = 0)", (gap_id, department, user_id, message_id, text))
            row = cur.fetchone()
            return row[0], bool(row[1])

    @staticmethod
    def attach_escalation(gap_id: str, escalation_id: str) -> None:
        with get_postgres_connection() as conn, conn.cursor() as cur:
            cur.execute("UPDATE knowledge_studio.knowledge_gaps SET escalation_id=%s WHERE id=%s", (escalation_id, gap_id))

    @staticmethod
    def _scope(org: str, dept: Optional[str]):
        clause, params = "d.organization_id = %s", [org]
        if dept:
            clause += " AND g.department_id = %s"
            params.append(dept)
        return clause, params

    @staticmethod
    def list_scoped(org: str, dept: Optional[str], status: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
        clause, params = KnowledgeGapRepository._scope(org, dept)
        if status:
            clause += " AND g.status = %s"
            params.append(status)
        with get_postgres_connection() as conn, conn.cursor() as cur:
            cur.execute(f"SELECT {GAP_COLS}, u.full_name {GAP_FROM} JOIN security.users u ON u.id = g.reported_by "
                        f"WHERE {clause} ORDER BY (g.status IN ('open','answered','drafting')) DESC, g.occurrences DESC, "
                        "g.updated_at DESC LIMIT %s", (*params, limit))
            rows = _gap_dicts(cur)
            for r in rows:
                r["reported_by_name"] = r.pop("full_name")
            return rows

    @staticmethod
    def mine(user_id: str, limit: int = 20) -> List[Dict[str, Any]]:
        with get_postgres_connection() as conn, conn.cursor() as cur:
            cur.execute("SELECT g.id, g.question, g.status, g.employee_reply, g.replied_at, g.created_at, g.updated_at "
                        "FROM knowledge_studio.knowledge_gaps g WHERE g.reported_by = %s "
                        "ORDER BY g.updated_at DESC LIMIT %s", (user_id, limit))
            return _gap_dicts(cur)

    @staticmethod
    def _get(cur, org: str, dept: Optional[str], gap_id: str, lock: bool = True) -> Dict[str, Any]:
        clause, params = KnowledgeGapRepository._scope(org, dept)
        suffix = " FOR UPDATE OF g" if lock else ""
        cur.execute(f"SELECT {GAP_COLS} {GAP_FROM} WHERE g.id = %s AND {clause}{suffix}", (gap_id, *params))
        rows = _gap_dicts(cur)
        if not rows:
            raise GapNotFound()
        return rows[0]

    @staticmethod
    def get(org, dept, gap_id: str) -> Dict[str, Any]:
        with get_postgres_connection() as conn, conn.cursor() as cur:
            return KnowledgeGapRepository._get(cur, org, dept, gap_id, lock=False)

    @staticmethod
    def reply(org, dept, gap_id: str, actor: str, text: str) -> Dict[str, Any]:
        with get_postgres_connection() as conn, conn.cursor() as cur:
            gap = KnowledgeGapRepository._get(cur, org, dept, gap_id)
            if gap["status"] in ("resolved", "dismissed"):
                raise DraftConflict("This question is already closed.")
            cur.execute("UPDATE knowledge_studio.knowledge_gaps SET employee_reply=%s, replied_by=%s, replied_at=now(), "
                        "status = CASE WHEN status='open' THEN 'answered' ELSE status END, updated_at=now() WHERE id=%s",
                        (text, actor, gap_id))
            return KnowledgeGapRepository._get(cur, org, dept, gap_id)

    @staticmethod
    def dismiss(org, dept, gap_id: str) -> Dict[str, Any]:
        with get_postgres_connection() as conn, conn.cursor() as cur:
            gap = KnowledgeGapRepository._get(cur, org, dept, gap_id)
            if gap["status"] in ("resolved", "dismissed"):
                raise DraftConflict("This question is already closed.")
            cur.execute("UPDATE knowledge_studio.knowledge_gaps SET status='dismissed', resolved_at=now(), updated_at=now() WHERE id=%s", (gap_id,))
            return KnowledgeGapRepository._get(cur, org, dept, gap_id)

    @staticmethod
    def link_draft(gap_id: str, draft_id: str) -> None:
        with get_postgres_connection() as conn, conn.cursor() as cur:
            cur.execute("UPDATE knowledge_studio.knowledge_gaps SET draft_id=%s, status='drafting', updated_at=now() WHERE id=%s",
                        (draft_id, gap_id))
            cur.execute("UPDATE knowledge_studio.procedure_drafts SET source_gap_id=%s WHERE id=%s", (gap_id, draft_id))

    @staticmethod
    def resolve_by_draft(draft_id: str) -> int:
        with get_postgres_connection() as conn, conn.cursor() as cur:
            cur.execute("UPDATE knowledge_studio.knowledge_gaps SET status='resolved', resolved_at=now(), updated_at=now() "
                        "WHERE draft_id=%s AND status IN ('open','answered','drafting')", (draft_id,))
            return cur.rowcount


class ApprovalRepository:
    """Manager approval of exact reviewed revisions."""

    @staticmethod
    def pending(department: str) -> List[Dict[str, Any]]:
        with get_postgres_connection() as conn:
            with conn.cursor() as cur:
                _start(cur, department)
                try:
                    cur.execute("SELECT " + COLUMNS + ", (SELECT question FROM knowledge_studio.knowledge_gaps g "
                                "WHERE g.id = procedure_drafts.source_gap_id) AS gap_question "
                                "FROM knowledge_studio.procedure_drafts WHERE department_id=%s AND status='reviewed' "
                                "AND published_version_id IS NULL ORDER BY reviewed_at DESC LIMIT 100", (department,))
                    names = [c.name.lower() for c in cur.description]
                    out = []
                    for r in cur.fetchall():
                        d = dict(zip(names, r))
                        for k in ("reviewed_at", "created_at", "updated_at", "approved_at"):
                            if d.get(k) is not None:
                                d[k] = d[k].isoformat()
                        d["approved"] = d["approved_by"] is not None and d["approved_revision"] == d["revision"]
                        out.append(d)
                    cur.execute("COMMIT")
                    return out
                except Exception:
                    cur.execute("ROLLBACK")
                    raise

    @staticmethod
    def decide(department: str, manager: str, draft_id: str, revision: int, approve: bool, note: str = ""):
        with get_postgres_connection() as conn:
            with conn.cursor() as cur:
                _start(cur, department)
                try:
                    cur.execute("SELECT " + COLUMNS + " FROM knowledge_studio.procedure_drafts "
                                "WHERE id=%s AND department_id=%s FOR UPDATE", (draft_id, department))
                    draft = _dict(cur)
                    if not draft:
                        raise DraftNotFound()
                    if draft["revision"] != revision or draft["status"] != "reviewed" or draft["published_version_id"]:
                        raise DraftConflict("Only the current, unpublished reviewed revision can be decided.")
                    if manager in (draft["reviewed_by"], draft["created_by"]):
                        raise DraftConflict("You cannot approve a draft you created or reviewed.")
                    if approve:
                        cur.execute("UPDATE knowledge_studio.procedure_drafts SET approved_by=%s, approved_at=now(), "
                                    "approved_revision=revision, rejection_note=NULL, updated_at=now() "
                                    "WHERE id=%s AND department_id=%s RETURNING " + COLUMNS, (manager, draft_id, department))
                        result = _dict(cur)
                        _event(cur, draft_id, department, manager, "approved", result["revision"])
                    else:
                        cur.execute("UPDATE knowledge_studio.procedure_drafts SET status='draft', revision=revision+1, "
                                    "approved_by=NULL, approved_at=NULL, approved_revision=NULL, rejection_note=%s, "
                                    "reviewed_by=NULL, reviewed_at=NULL, updated_at=now() "
                                    "WHERE id=%s AND department_id=%s RETURNING " + COLUMNS, (note, draft_id, department))
                        result = _dict(cur)
                        _event(cur, draft_id, department, manager, "returned", result["revision"])
                    cur.execute("COMMIT")
                    return result
                except Exception:
                    cur.execute("ROLLBACK")
                    raise
