"""Cases: an employee's request for human help, an unanswered question, or a reported incorrect answer - one thread each.

Staff scope: an admin acts on their organization, a manager on their own department (resolved by the API layer from the
database and passed in). An out-of-scope id behaves exactly like a missing one. Employees only ever reach their own cases,
and never see internal notes. A staff reply is a reply: it is not stored as organizational knowledge.
"""
from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

from app.core.database import get_postgres_connection, get_transaction

PUBLIC_STATUS = {"open": "open", "in_progress": "in_progress", "answered": "in_progress", "drafting": "in_progress",
                 "resolved": "resolved", "closed": "closed", "dismissed": "closed"}
COLS = ("g.id, g.kind, g.title, g.question, g.status, g.priority, g.department_id, g.reported_by, g.assigned_to, "
        "g.escalated_to_manager, g.conversation_id, g.draft_id, g.occurrences, g.created_at, g.updated_at, g.resolved_at, "
        "g.acknowledged_at")
FROM = ("FROM knowledge_studio.knowledge_gaps g JOIN security.departments d ON d.id = g.department_id "
        "LEFT JOIN security.users ru ON ru.id = g.reported_by LEFT JOIN security.users au ON au.id = g.assigned_to")
NAMES = "COALESCE(ru.full_name, ru.email) AS reporter_name, COALESCE(au.full_name, au.email) AS assignee_name"


class CaseNotFound(Exception):
    pass


class CaseConflict(Exception):
    pass


def _iso(row: Dict[str, Any]) -> Dict[str, Any]:
    for key in ("created_at", "updated_at", "resolved_at", "acknowledged_at"):
        if row.get(key) is not None:
            row[key] = row[key].isoformat()
    return row


def _rows(cur) -> List[Dict[str, Any]]:
    names = [c.name for c in cur.description]
    return [_iso(dict(zip(names, r))) for r in cur.fetchall()]


def _present(row: Dict[str, Any]) -> Dict[str, Any]:
    row["public_status"] = PUBLIC_STATUS.get(row["status"], row["status"])
    row["title"] = row.get("title") or row["question"]
    return row


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


class CaseRepository:
    # ---------- creation ----------
    @staticmethod
    def create_for_employee(user: Dict[str, Any], conversation_id: str, kind: str, title: str, note: str,
                            context_message_ids: Optional[List[str]] = None, priority: str = "normal") -> Dict[str, Any]:
        """Create a case from the employee's own conversation. Only the messages they confirm are copied as context."""
        case_id = _new_id("case")
        with get_transaction() as cur:
            cur.execute("SELECT department_id FROM workmate_copilot.conversations WHERE id=%s AND user_id=%s",
                        (conversation_id, user["sub"]))
            row = cur.fetchone()
            if not row:
                raise CaseNotFound()
            dept = row[0]
            clean = " ".join(title.split())[:200] or "Request for help"
            cur.execute(
                "INSERT INTO knowledge_studio.knowledge_gaps (id, department_id, reported_by, question, kind, title, "
                "conversation_id, priority) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                (case_id, dept, user["sub"], clean[:1000], kind, clean, conversation_id, priority))
            ids = context_message_ids or []
            if ids:
                cur.execute("SELECT sender, message_text FROM workmate_copilot.conversation_messages "
                            "WHERE conversation_id=%s AND id = ANY(%s) ORDER BY created_at", (conversation_id, ids))
                transcript = "\n".join(("Employee: " if s == "employee" else "WorkMate: ") + (t or "")[:700]
                                       for s, t in cur.fetchall())[:3800]
                if transcript:
                    cur.execute("INSERT INTO knowledge_studio.case_messages (id, case_id, author_id, author_role, kind, body) "
                                "VALUES (%s,%s,%s,'employee','context',%s)", (_new_id("cm"), case_id, user["sub"], transcript))
            if note.strip():
                cur.execute("INSERT INTO knowledge_studio.case_messages (id, case_id, author_id, author_role, body) "
                            "VALUES (%s,%s,%s,'employee',%s)", (_new_id("cm"), case_id, user["sub"], note.strip()[:2000]))
        return CaseRepository.get_mine(user["sub"], case_id)

    # ---------- employee side ----------
    @staticmethod
    def mine(user_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        with get_postgres_connection() as conn, conn.cursor() as cur:
            cur.execute(
                f"SELECT {COLS}, {NAMES}, "
                "(SELECT body FROM knowledge_studio.case_messages m WHERE m.case_id=g.id AND NOT m.internal AND m.kind='message' "
                "   AND m.author_role <> 'employee' ORDER BY m.created_at DESC LIMIT 1) AS latest_reply, "
                "(SELECT COALESCE(g.employee_reply,'')) AS legacy_reply "
                f"{FROM} WHERE g.reported_by=%s ORDER BY g.updated_at DESC LIMIT %s", (user_id, limit))
            out = []
            for r in _rows(cur):
                r["latest_reply"] = r["latest_reply"] or r.pop("legacy_reply") or None
                r.pop("legacy_reply", None)
                out.append(_present(r))
            return out

    @staticmethod
    def _owned(cur, user_id: str, case_id: str, lock: bool = False) -> Dict[str, Any]:
        cur.execute(f"SELECT {COLS}, {NAMES} {FROM} WHERE g.id=%s AND g.reported_by=%s" + (" FOR UPDATE OF g" if lock else ""),
                    (case_id, user_id))
        rows = _rows(cur)
        if not rows:
            raise CaseNotFound()
        return _present(rows[0])

    @staticmethod
    def get_mine(user_id: str, case_id: str) -> Dict[str, Any]:
        with get_postgres_connection() as conn, conn.cursor() as cur:
            case = CaseRepository._owned(cur, user_id, case_id)
            case["thread"] = CaseRepository._thread(cur, case_id, include_internal=False)
            return case

    @staticmethod
    def employee_message(user_id: str, case_id: str, body: str) -> Dict[str, Any]:
        with get_transaction() as cur:
            case = CaseRepository._owned(cur, user_id, case_id, lock=True)
            if case["status"] in ("closed", "dismissed"):
                raise CaseConflict("This request is closed. Please start a new one.")
            cur.execute("INSERT INTO knowledge_studio.case_messages (id, case_id, author_id, author_role, body) "
                        "VALUES (%s,%s,%s,'employee',%s)", (_new_id("cm"), case_id, user_id, body.strip()))
            # More information from the employee reopens a resolved case and tells staff there is something new.
            cur.execute("UPDATE knowledge_studio.knowledge_gaps SET updated_at=now(), "
                        "status = CASE WHEN status IN ('resolved','answered') THEN 'open' ELSE status END, "
                        "resolved_at = CASE WHEN status='resolved' THEN NULL ELSE resolved_at END WHERE id=%s", (case_id,))
        return CaseRepository.get_mine(user_id, case_id)

    @staticmethod
    def acknowledge(user_id: str, case_id: str) -> Dict[str, Any]:
        with get_transaction() as cur:
            case = CaseRepository._owned(cur, user_id, case_id, lock=True)
            if case["status"] != "resolved":
                raise CaseConflict("Only a resolved request can be acknowledged.")
            cur.execute("UPDATE knowledge_studio.knowledge_gaps SET status='closed', acknowledged_at=now(), updated_at=now() "
                        "WHERE id=%s", (case_id,))
        return CaseRepository.get_mine(user_id, case_id)

    # ---------- staff side ----------
    @staticmethod
    def _scope(org: str, dept: Optional[str]):
        clause, params = "d.organization_id = %s", [org]
        if dept:
            clause += " AND g.department_id = %s"
            params.append(dept)
        return clause, params

    @staticmethod
    def list_staff(org: str, dept: Optional[str], view: str = "all", q: str = "", manager_view: bool = False,
                   assignee: Optional[str] = None, priority: Optional[str] = None, department: Optional[str] = None,
                   limit: int = 100) -> List[Dict[str, Any]]:
        clause, params = CaseRepository._scope(org, dept)
        if view == "escalated":
            clause += " AND (g.kind IN ('human_request','incorrect_answer') OR g.escalated_to_manager) AND g.status NOT IN ('resolved','closed','dismissed')"
        elif view == "unanswered":
            clause += " AND g.kind = 'unanswered' AND g.status NOT IN ('resolved','closed','dismissed')"
        elif view == "resolved":
            clause += " AND g.status IN ('resolved','closed','dismissed')"
        if manager_view:
            clause += " AND (g.escalated_to_manager OR g.priority IN ('high','urgent'))"
        if q.strip():
            clause += " AND (g.question ILIKE %s OR COALESCE(g.title,'') ILIKE %s OR COALESCE(ru.full_name,'') ILIKE %s)"
            like = f"%{q.strip()[:80]}%"
            params += [like, like, like]
        if assignee:
            clause += " AND g.assigned_to = %s"
            params.append(assignee)
        if priority:
            clause += " AND g.priority = %s"
            params.append(priority)
        if department:
            clause += " AND g.department_id = %s"
            params.append(department)
        with get_postgres_connection() as conn, conn.cursor() as cur:
            cur.execute(f"SELECT {COLS}, {NAMES}, "
                        "(SELECT count(*) FROM knowledge_studio.case_messages m WHERE m.case_id=g.id AND m.kind='message') AS messages "
                        f"{FROM} WHERE {clause} ORDER BY (g.status IN ('resolved','closed','dismissed')), "
                        "CASE g.priority WHEN 'urgent' THEN 0 WHEN 'high' THEN 1 WHEN 'normal' THEN 2 ELSE 3 END, g.updated_at DESC "
                        "LIMIT %s", (*params, limit))
            return [_present(r) for r in _rows(cur)]

    @staticmethod
    def counts(org: str, dept: Optional[str]) -> Dict[str, int]:
        clause, params = CaseRepository._scope(org, dept)
        open_ = "g.status NOT IN ('resolved','closed','dismissed')"
        with get_postgres_connection() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT count(*), "
                f"count(*) FILTER (WHERE {open_} AND (g.kind IN ('human_request','incorrect_answer') OR g.escalated_to_manager)), "
                f"count(*) FILTER (WHERE {open_} AND g.kind='unanswered'), "
                "count(*) FILTER (WHERE g.status IN ('resolved','closed','dismissed')), "
                f"count(*) FILTER (WHERE {open_} AND (g.escalated_to_manager OR g.priority IN ('high','urgent'))) "
                f"{FROM} WHERE {clause}", params)
            a, e, u, r, m = cur.fetchone()
            return {"all": a, "escalated": e, "unanswered": u, "resolved": r, "manager_open": m}

    @staticmethod
    def _staff_case(cur, org: str, dept: Optional[str], case_id: str, lock: bool = False) -> Dict[str, Any]:
        clause, params = CaseRepository._scope(org, dept)
        cur.execute(f"SELECT {COLS}, {NAMES} {FROM} WHERE g.id=%s AND {clause}" + (" FOR UPDATE OF g" if lock else ""),
                    (case_id, *params))
        rows = _rows(cur)
        if not rows:
            raise CaseNotFound()
        return _present(rows[0])

    @staticmethod
    def _thread(cur, case_id: str, include_internal: bool) -> List[Dict[str, Any]]:
        cur.execute("SELECT m.id, m.kind, m.body, m.internal, m.author_role, m.created_at, COALESCE(u.full_name, u.email) AS author "
                    "FROM knowledge_studio.case_messages m JOIN security.users u ON u.id = m.author_id "
                    "WHERE m.case_id=%s" + ("" if include_internal else " AND NOT m.internal") + " ORDER BY m.created_at, m.id",
                    (case_id,))
        return _rows(cur)

    @staticmethod
    def get_staff(org: str, dept: Optional[str], case_id: str) -> Dict[str, Any]:
        with get_postgres_connection() as conn, conn.cursor() as cur:
            case = CaseRepository._staff_case(cur, org, dept, case_id)
            case["thread"] = CaseRepository._thread(cur, case_id, include_internal=True)
            return case

    @staticmethod
    def staff_message(org: str, dept: Optional[str], actor: Dict[str, Any], case_id: str, body: str, internal: bool) -> Dict[str, Any]:
        role = "admin" if actor.get("role") == "admin" else "manager"
        with get_transaction() as cur:
            case = CaseRepository._staff_case(cur, org, dept, case_id, lock=True)
            if case["status"] in ("closed", "dismissed"):
                raise CaseConflict("This case is closed.")
            cur.execute("INSERT INTO knowledge_studio.case_messages (id, case_id, author_id, author_role, body, internal) "
                        "VALUES (%s,%s,%s,%s,%s,%s)", (_new_id("cm"), case_id, actor["sub"], role, body.strip(), internal))
            if not internal:
                cur.execute("UPDATE knowledge_studio.knowledge_gaps SET updated_at=now(), "
                            "status = CASE WHEN status IN ('open','answered') THEN 'in_progress' ELSE status END, "
                            "assigned_to = COALESCE(assigned_to, %s), "
                            "employee_reply = %s, replied_by = %s, replied_at = now() WHERE id=%s",
                            (actor["sub"], body.strip()[:1500], actor["sub"], case_id))
            else:
                cur.execute("UPDATE knowledge_studio.knowledge_gaps SET updated_at=now() WHERE id=%s", (case_id,))
        return CaseRepository.get_staff(org, dept, case_id)

    @staticmethod
    def assign(org: str, dept: Optional[str], case_id: str, assignee_id: Optional[str]) -> Dict[str, Any]:
        with get_transaction() as cur:
            case = CaseRepository._staff_case(cur, org, dept, case_id, lock=True)
            if assignee_id:
                cur.execute("SELECT 1 FROM security.users u JOIN security.departments d ON d.id=u.department_id "
                            "JOIN security.user_roles ur ON ur.user_id=u.id JOIN security.roles r ON r.id=ur.role_id "
                            "WHERE u.id=%s AND d.organization_id=%s AND u.status='active' AND lower(r.name) IN ('admin','manager')",
                            (assignee_id, org))
                if not cur.fetchone():
                    raise CaseConflict("That person cannot be assigned to cases in this organization.")
            cur.execute("UPDATE knowledge_studio.knowledge_gaps SET assigned_to=%s::varchar, updated_at=now(), "
                        "status = CASE WHEN status='open' AND %s::varchar IS NOT NULL THEN 'in_progress' ELSE status END WHERE id=%s",
                        (assignee_id, assignee_id, case_id))
        return CaseRepository.get_staff(org, dept, case_id)

    @staticmethod
    def update_flags(org: str, dept: Optional[str], case_id: str, priority: Optional[str], escalate: Optional[bool]) -> Dict[str, Any]:
        with get_transaction() as cur:
            CaseRepository._staff_case(cur, org, dept, case_id, lock=True)
            if priority:
                cur.execute("UPDATE knowledge_studio.knowledge_gaps SET priority=%s, updated_at=now() WHERE id=%s", (priority, case_id))
            if escalate is not None:
                cur.execute("UPDATE knowledge_studio.knowledge_gaps SET escalated_to_manager=%s, "
                            "priority = CASE WHEN %s::boolean AND priority IN ('low','normal') THEN 'high' ELSE priority END, "
                            "updated_at=now() WHERE id=%s", (escalate, escalate, case_id))
        return CaseRepository.get_staff(org, dept, case_id)

    @staticmethod
    def resolve(org: str, dept: Optional[str], actor: Dict[str, Any], case_id: str, note: str) -> Dict[str, Any]:
        role = "admin" if actor.get("role") == "admin" else "manager"
        with get_transaction() as cur:
            case = CaseRepository._staff_case(cur, org, dept, case_id, lock=True)
            if case["status"] in ("resolved", "closed", "dismissed"):
                raise CaseConflict("This case is already closed.")
            if note.strip():
                cur.execute("INSERT INTO knowledge_studio.case_messages (id, case_id, author_id, author_role, body) "
                            "VALUES (%s,%s,%s,%s,%s)", (_new_id("cm"), case_id, actor["sub"], role, note.strip()))
            cur.execute("UPDATE knowledge_studio.knowledge_gaps SET status='resolved', resolved_at=now(), updated_at=now(), "
                        "assigned_to=COALESCE(assigned_to,%s), employee_reply=COALESCE(NULLIF(%s,''), employee_reply), "
                        "replied_by=%s, replied_at=now() WHERE id=%s",
                        (actor["sub"], note.strip()[:1500], actor["sub"], case_id))
        return CaseRepository.get_staff(org, dept, case_id)

    @staticmethod
    def staff_directory(org: str, dept: Optional[str]) -> List[Dict[str, Any]]:
        with get_postgres_connection() as conn, conn.cursor() as cur:
            cur.execute("SELECT DISTINCT u.id, COALESCE(u.full_name, u.email) AS name, lower(r.name) AS role "
                        "FROM security.users u JOIN security.departments d ON d.id=u.department_id "
                        "JOIN security.user_roles ur ON ur.user_id=u.id JOIN security.roles r ON r.id=ur.role_id "
                        "WHERE d.organization_id=%s AND u.status='active' AND lower(r.name) IN ('admin','manager') "
                        + ("AND (u.department_id=%s OR lower(r.name)='admin') " if dept else "") + "ORDER BY name",
                        (org, dept) if dept else (org,))
            return [{"id": r[0], "name": r[1], "role": r[2]} for r in cur.fetchall()]
