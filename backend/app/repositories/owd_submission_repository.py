"""Pending direct OWD uploads awaiting manager approval."""
from __future__ import annotations

import hashlib
import uuid
from typing import Any, Dict, List, Optional

from app.core.database import get_postgres_connection


class SubmissionNotFound(Exception):
    pass


class SubmissionConflict(Exception):
    pass


COLS = ("id, department_id, uploaded_by, filename, title, workflow_code, version_hint, sha256, status, "
        "decision_note, decided_by, decided_at, published_version_id, created_at")


def _row(cur) -> Optional[Dict[str, Any]]:
    r = cur.fetchone()
    if r is None:
        return None
    d = dict(zip([c.name for c in cur.description], r))
    for k in ("decided_at", "created_at"):
        if d.get(k) is not None:
            d[k] = d[k].isoformat()
    return d


def _rows(cur) -> List[Dict[str, Any]]:
    names = [c.name for c in cur.description]
    out = []
    for r in cur.fetchall():
        d = dict(zip(names, r))
        for k in ("decided_at", "created_at"):
            if d.get(k) is not None:
                d[k] = d[k].isoformat()
        out.append(d)
    return out


class OwdSubmissionRepository:
    @staticmethod
    def stage(department: str, uploader: str, filename: str, title: str, raw: bytes,
              workflow_code: str, version_hint: int) -> Dict[str, Any]:
        sub_id = f"owdsub_{uuid.uuid4().hex[:16]}"
        digest = hashlib.sha256(raw).hexdigest()
        with get_postgres_connection() as conn, conn.cursor() as cur:
            cur.execute("SELECT id FROM knowledge_studio.owd_submissions "
                        "WHERE department_id=%s AND sha256=%s AND status='pending'", (department, digest))
            existing = cur.fetchone()
            if existing:
                raise SubmissionConflict("This exact file is already waiting for approval.")
            cur.execute("INSERT INTO knowledge_studio.owd_submissions "
                        "(id,department_id,uploaded_by,filename,title,workflow_code,version_hint,sha256,content) "
                        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING " + COLS,
                        (sub_id, department, uploader, filename[:255], title[:512], workflow_code[:128],
                         version_hint, digest, raw))
            return _row(cur)

    @staticmethod
    def list_for_departments(departments: List[str], status: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
        with get_postgres_connection() as conn, conn.cursor() as cur:
            sql = f"SELECT {COLS} FROM knowledge_studio.owd_submissions WHERE department_id = ANY(%s)"
            params: list = [list(departments)]
            if status:
                sql += " AND status=%s"
                params.append(status)
            cur.execute(sql + " ORDER BY created_at DESC LIMIT %s", (*params, limit))
            return _rows(cur)

    @staticmethod
    def get_locked(cur, department: str, sub_id: str) -> Dict[str, Any]:
        cur.execute(f"SELECT {COLS}, content FROM knowledge_studio.owd_submissions "
                    "WHERE id=%s AND department_id=%s FOR UPDATE", (sub_id, department))
        r = cur.fetchone()
        if r is None:
            raise SubmissionNotFound()
        names = [c.name for c in cur.description]
        d = dict(zip(names, r))
        d["content"] = bytes(d["content"])
        return d

    @staticmethod
    def mark_returned(department: str, manager: str, sub_id: str, note: str) -> Dict[str, Any]:
        with get_postgres_connection() as conn, conn.cursor() as cur:
            sub = OwdSubmissionRepository.get_locked(cur, department, sub_id)
            if sub["status"] != "pending":
                raise SubmissionConflict("This submission was already decided.")
            if sub["uploaded_by"] == manager:
                raise SubmissionConflict("You cannot decide a file you uploaded.")
            cur.execute("UPDATE knowledge_studio.owd_submissions SET status='returned', decision_note=%s, "
                        "decided_by=%s, decided_at=now() WHERE id=%s RETURNING " + COLS, (note, manager, sub_id))
            return _row(cur)

    @staticmethod
    def mark_published(cur, sub_id: str, manager: str, version_id: str) -> Dict[str, Any]:
        cur.execute("UPDATE knowledge_studio.owd_submissions SET status='published', decided_by=%s, decided_at=now(), "
                    "published_version_id=%s WHERE id=%s RETURNING " + COLS, (manager, version_id, sub_id))
        return _row(cur)
