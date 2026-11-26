"""Requests for human help ("cases"), answer feedback, and conversation history management.

Employees: raise a request from their own conversation, follow its thread, add information, acknowledge a resolution.
Admins and managers: review the cases in their scope, reply, add internal notes, assign, escalate, resolve.
A staff reply is a reply to the employee. It never becomes organizational knowledge.
"""
from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from starlette.concurrency import run_in_threadpool

from app.core.database import get_postgres_connection, get_transaction
from app.middleware.auth_middleware import get_current_user
from app.middleware.rbac_middleware import require_role
from app.repositories.case_repository import CaseConflict, CaseNotFound, CaseRepository
from app.repositories.org_repository import organization_of_user

router = APIRouter(tags=["Cases"])


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EscalateBody(Strict):
    conversation_id: str = Field(min_length=3, max_length=64)
    note: str = Field(default="", max_length=2000)
    message_ids: List[str] = Field(default_factory=list, max_length=12)


class FeedbackBody(Strict):
    message_id: str = Field(min_length=3, max_length=64)
    rating: Literal["helpful", "not_helpful"]
    note: str = Field(default="", max_length=500)


class MessageBody(Strict):
    body: str = Field(min_length=1, max_length=2000)
    internal: bool = False


class AssignBody(Strict):
    assignee_id: Optional[str] = Field(default=None, max_length=64)


class FlagsBody(Strict):
    priority: Optional[Literal["low", "normal", "high", "urgent"]] = None
    escalate_to_manager: Optional[bool] = None


class ResolveBody(Strict):
    note: str = Field(default="", max_length=1500)


class ConversationPatch(Strict):
    title: Optional[str] = Field(default=None, min_length=1, max_length=160)
    archived: Optional[bool] = None


def _scope(user: Dict[str, Any]) -> tuple[str, Optional[str]]:
    with get_postgres_connection() as conn, conn.cursor() as cur:
        org = organization_of_user(cur, user["sub"])
    if not org:
        raise HTTPException(403, detail={"error_code": "ORG_NOT_CONFIGURED", "message": "No organization scope."})
    return org, (None if user.get("role") == "admin" else user.get("department_id"))


async def _guard(fn, *args, **kwargs):
    try:
        return await run_in_threadpool(lambda: fn(*args, **kwargs))
    except CaseNotFound as exc:
        raise HTTPException(404, detail={"error_code": "NOT_FOUND", "message": "Not found."}) from exc
    except CaseConflict as exc:
        raise HTTPException(409, detail={"error_code": "CONFLICT", "message": str(exc)}) from exc


# ---------------------------------------------------------------- employee
def _last_question(conversation_id: str, user_id: str) -> str:
    with get_postgres_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT m.message_text FROM workmate_copilot.conversation_messages m "
                    "JOIN workmate_copilot.conversations c ON c.id=m.conversation_id "
                    "WHERE m.conversation_id=%s AND c.user_id=%s AND m.sender='employee' ORDER BY m.created_at DESC LIMIT 1",
                    (conversation_id, user_id))
        row = cur.fetchone()
    if row is None:
        raise CaseNotFound()
    return row[0]


def _with_preceding_questions(conversation_id: str, user_id: str, message_ids: List[str]) -> List[str]:
    """Share the chosen messages plus the employee question each assistant answer responded to (own conversation only)."""
    if not message_ids:
        return []
    with get_postgres_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT m.id, (SELECT q.id FROM workmate_copilot.conversation_messages q WHERE q.conversation_id=m.conversation_id "
            "AND q.sender='employee' AND q.created_at <= m.created_at ORDER BY q.created_at DESC LIMIT 1) "
            "FROM workmate_copilot.conversation_messages m JOIN workmate_copilot.conversations c ON c.id=m.conversation_id "
            "WHERE m.conversation_id=%s AND c.user_id=%s AND m.id = ANY(%s)", (conversation_id, user_id, message_ids))
        out: List[str] = []
        for mid, qid in cur.fetchall():
            for x in (qid, mid):
                if x and x not in out:
                    out.append(x)
        return out


@router.post("/copilot/escalate", status_code=201)
async def ask_a_person(body: EscalateBody, user: Dict[str, Any] = Depends(require_role("employee", "manager", "admin"))):
    """Raise a request for a person. Only the conversation messages the employee selected are shared with staff."""
    question = await _guard(_last_question, body.conversation_id, user["sub"])
    ids = await _guard(_with_preceding_questions, body.conversation_id, user["sub"], body.message_ids)
    return await _guard(CaseRepository.create_for_employee, user, body.conversation_id, "human_request", question,
                        body.note, ids)


def _record_feedback(user: Dict[str, Any], body: FeedbackBody) -> Dict[str, Any]:
    with get_postgres_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT m.conversation_id, c.department_id FROM workmate_copilot.conversation_messages m "
                    "JOIN workmate_copilot.conversations c ON c.id=m.conversation_id "
                    "WHERE m.id=%s AND c.user_id=%s AND m.sender='ai'", (body.message_id, user["sub"]))
        row = cur.fetchone()
        if not row:
            raise CaseNotFound()
        conversation_id, dept = row
        cur.execute("INSERT INTO workmate_copilot.message_feedback (message_id, user_id, department_id, rating, note) "
                    "VALUES (%s,%s,%s,%s,%s) ON CONFLICT (message_id, user_id) DO UPDATE SET rating=EXCLUDED.rating, "
                    "note=EXCLUDED.note, created_at=now()", (body.message_id, user["sub"], dept, body.rating, body.note.strip() or None))
        cur.execute("SELECT m2.id, m2.message_text FROM workmate_copilot.conversation_messages m2 "
                    "WHERE m2.conversation_id=%s AND m2.sender='employee' AND m2.created_at <= "
                    "(SELECT created_at FROM workmate_copilot.conversation_messages WHERE id=%s) ORDER BY m2.created_at DESC LIMIT 1",
                    (conversation_id, body.message_id))
        question = cur.fetchone()
    result: Dict[str, Any] = {"rating": body.rating, "case_id": None}
    if body.rating == "not_helpful" and question:
        with get_postgres_connection() as conn, conn.cursor() as cur:
            cur.execute("SELECT 1 FROM knowledge_studio.knowledge_gaps g WHERE g.reported_by=%s AND g.kind='incorrect_answer' "
                        "AND g.conversation_id=%s AND g.question=%s AND g.status NOT IN ('resolved','closed','dismissed') LIMIT 1",
                        (user["sub"], conversation_id, " ".join(question[1].split())[:1000]))
            existing = cur.fetchone()
        if not existing:
            case = CaseRepository.create_for_employee(
                user, conversation_id, "incorrect_answer", question[1], body.note or "The employee marked this answer as not helpful.",
                [question[0], body.message_id])
            result["case_id"] = case["id"]
    return result


@router.post("/copilot/feedback", status_code=201)
async def rate_answer(body: FeedbackBody, user: Dict[str, Any] = Depends(require_role("employee", "manager", "admin"))):
    """Helpful / not helpful. 'Not helpful' also flags the answer for staff review as a case."""
    return await _guard(_record_feedback, user, body)


@router.get("/my/cases")
async def my_cases(user: Dict[str, Any] = Depends(require_role("employee", "manager", "admin"))):
    return {"items": await _guard(CaseRepository.mine, user["sub"])}


@router.get("/my/cases/{case_id}")
async def my_case(case_id: str, user: Dict[str, Any] = Depends(require_role("employee", "manager", "admin"))):
    return await _guard(CaseRepository.get_mine, user["sub"], case_id)


@router.post("/my/cases/{case_id}/messages", status_code=201)
async def my_case_message(case_id: str, body: MessageBody, user: Dict[str, Any] = Depends(require_role("employee", "manager", "admin"))):
    return await _guard(CaseRepository.employee_message, user["sub"], case_id, body.body)


@router.post("/my/cases/{case_id}/acknowledge")
async def my_case_acknowledge(case_id: str, user: Dict[str, Any] = Depends(require_role("employee", "manager", "admin"))):
    return await _guard(CaseRepository.acknowledge, user["sub"], case_id)


# ---------------------------------------------------------------- staff
@router.get("/cases")
async def list_cases(view: Literal["all", "escalated", "unanswered", "resolved"] = "all", q: str = Query("", max_length=80),
                     managed: bool = False, assignee: Optional[str] = Query(None, max_length=64),
                     priority: Optional[Literal["low", "normal", "high", "urgent"]] = None,
                     department: Optional[str] = Query(None, max_length=64), limit: int = Query(100, ge=1, le=200),
                     user: Dict[str, Any] = Depends(require_role("admin", "manager"))):
    org, dept = await run_in_threadpool(_scope, user)
    items = await _guard(CaseRepository.list_staff, org, dept, view, q, managed and user["role"] == "manager",
                         assignee, priority, department, limit)
    return {"items": items, "counts": await _guard(CaseRepository.counts, org, dept)}


@router.get("/cases/people")
async def case_people(user: Dict[str, Any] = Depends(require_role("admin", "manager"))):
    org, dept = await run_in_threadpool(_scope, user)
    return {"items": await _guard(CaseRepository.staff_directory, org, dept)}


@router.get("/cases/{case_id}")
async def get_case(case_id: str, user: Dict[str, Any] = Depends(require_role("admin", "manager"))):
    org, dept = await run_in_threadpool(_scope, user)
    return await _guard(CaseRepository.get_staff, org, dept, case_id)


@router.post("/cases/{case_id}/messages", status_code=201)
async def case_message(case_id: str, body: MessageBody, user: Dict[str, Any] = Depends(require_role("admin", "manager"))):
    org, dept = await run_in_threadpool(_scope, user)
    return await _guard(CaseRepository.staff_message, org, dept, user, case_id, body.body, body.internal)


@router.post("/cases/{case_id}/assign")
async def case_assign(case_id: str, body: AssignBody, user: Dict[str, Any] = Depends(require_role("admin", "manager"))):
    org, dept = await run_in_threadpool(_scope, user)
    return await _guard(CaseRepository.assign, org, dept, case_id, body.assignee_id)


@router.post("/cases/{case_id}/flags")
async def case_flags(case_id: str, body: FlagsBody, user: Dict[str, Any] = Depends(require_role("admin", "manager"))):
    org, dept = await run_in_threadpool(_scope, user)
    return await _guard(CaseRepository.update_flags, org, dept, case_id, body.priority, body.escalate_to_manager)


@router.post("/cases/{case_id}/resolve")
async def case_resolve(case_id: str, body: ResolveBody, user: Dict[str, Any] = Depends(require_role("admin", "manager"))):
    org, dept = await run_in_threadpool(_scope, user)
    return await _guard(CaseRepository.resolve, org, dept, user, case_id, body.note)


# ---------------------------------------------------------------- conversation history (employee's own)
@router.get("/copilot/conversations")
async def my_conversations(q: str = Query("", max_length=80), archived: bool = False, limit: int = Query(60, ge=1, le=100),
                           user: Dict[str, Any] = Depends(require_role("employee", "manager", "admin"))):
    def work():
        like = f"%{q.strip()}%" if q.strip() else None
        with get_postgres_connection() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT c.id, c.title, c.started_at, c.archived_at, "
                " (SELECT message_text FROM workmate_copilot.conversation_messages m WHERE m.conversation_id=c.id AND m.sender='employee' ORDER BY m.created_at LIMIT 1) AS first_question, "
                " (SELECT message_text FROM workmate_copilot.conversation_messages m WHERE m.conversation_id=c.id ORDER BY m.created_at DESC LIMIT 1) AS last_text, "
                " (SELECT max(created_at) FROM workmate_copilot.conversation_messages m WHERE m.conversation_id=c.id) AS last_activity, "
                " (SELECT count(*) FROM workmate_copilot.conversation_messages m WHERE m.conversation_id=c.id) AS messages "
                "FROM workmate_copilot.conversations c WHERE c.user_id=%s AND ((c.archived_at IS NOT NULL) = %s) "
                "AND EXISTS (SELECT 1 FROM workmate_copilot.conversation_messages m WHERE m.conversation_id=c.id) "
                "AND (%s::text IS NULL OR COALESCE(c.title,'') ILIKE %s OR EXISTS (SELECT 1 FROM workmate_copilot.conversation_messages m "
                "     WHERE m.conversation_id=c.id AND m.message_text ILIKE %s)) "
                "ORDER BY last_activity DESC NULLS LAST LIMIT %s", (user["sub"], archived, like, like, like, limit))
            out = []
            for cid, title, started, arch, first_q, last_text, last_act, count in cur.fetchall():
                shown = (title or first_q or "New conversation").strip()
                out.append({"id": cid, "title": shown[:90] + ("…" if len(shown) > 90 else ""), "custom_title": bool(title),
                            "preview": (last_text or "")[:140], "last_activity": (last_act or started).isoformat(),
                            "messages": count, "archived": arch is not None})
            return out
    return {"items": await run_in_threadpool(work)}


@router.patch("/copilot/conversations/{conversation_id}")
async def patch_conversation(conversation_id: str, body: ConversationPatch,
                             user: Dict[str, Any] = Depends(require_role("employee", "manager", "admin"))):
    """Rename or archive. Archiving hides the conversation from the employee; the record is kept for audit and analytics."""
    if body.title is None and body.archived is None:
        raise HTTPException(422, detail={"error_code": "NOTHING_TO_CHANGE", "message": "Send a title or archived."})

    def work():
        with get_transaction() as cur:
            cur.execute("SELECT 1 FROM workmate_copilot.conversations WHERE id=%s AND user_id=%s FOR UPDATE", (conversation_id, user["sub"]))
            if not cur.fetchone():
                raise CaseNotFound()
            if body.title is not None:
                cur.execute("UPDATE workmate_copilot.conversations SET title=%s WHERE id=%s", (" ".join(body.title.split()), conversation_id))
            if body.archived is not None:
                cur.execute("UPDATE workmate_copilot.conversations SET archived_at = CASE WHEN %s THEN now() ELSE NULL END WHERE id=%s",
                            (body.archived, conversation_id))
        return {"id": conversation_id, "updated": True}
    return await _guard(work)


@router.get("/copilot/suggestions")
async def suggested_questions(limit: int = Query(4, ge=1, le=8),
                              user: Dict[str, Any] = Depends(require_role("employee", "manager", "admin"))):
    """Starter questions drawn from published SOPs in the caller's department - most-used first, never invented."""
    def work():
        with get_postgres_connection() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT w.title, count(ws.id) AS used FROM knowledge_studio.workflows w "
                "JOIN knowledge_studio.workflow_versions wv ON wv.workflow_id=w.id AND lower(wv.status)='published' "
                "LEFT JOIN workmate_copilot.workflow_sessions ws ON ws.workflow_version_id=wv.id "
                "WHERE w.department_id=%s GROUP BY w.title ORDER BY used DESC, w.title LIMIT %s",
                (user.get("department_id"), limit))
            return [{"title": t, "question": t} for t, _ in cur.fetchall()]
    return {"items": await run_in_threadpool(work)}
