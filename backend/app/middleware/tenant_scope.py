"""Which departments may this caller act on?

An administrator may manage knowledge only in departments of their own
organization; anyone whose department has no organization is limited to that one
department. Out-of-scope ids are reported as 404 so existence is never disclosed.
"""
from __future__ import annotations

from typing import Any, Dict, FrozenSet

from fastapi import Depends, HTTPException, status
from starlette.concurrency import run_in_threadpool

from app.core.database import get_postgres_connection
from app.middleware.auth_middleware import get_current_user


class DepartmentScope:
    def __init__(self, allowed: FrozenSet[str]):
        self.allowed = allowed

    def ensure(self, department_id: str | None) -> str:
        if not department_id or department_id not in self.allowed:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"error_code": "NOT_FOUND", "message": "Not found in your organization.", "details": None},
            )
        return department_id


def _load(user_id: str, own_department: str) -> FrozenSet[str]:
    with get_postgres_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT d.organization_id FROM security.users u JOIN security.departments d ON d.id = u.department_id "
                    "WHERE u.id = %s", (user_id,))
        row = cur.fetchone()
        org = row[0] if row else None
        if not org:
            return frozenset({own_department}) if own_department else frozenset()
        cur.execute("SELECT id FROM security.departments WHERE organization_id = %s", (org,))
        return frozenset(r[0] for r in cur.fetchall())


async def department_scope(user: Dict[str, Any] = Depends(get_current_user)) -> DepartmentScope:
    allowed = await run_in_threadpool(_load, str(user.get("sub") or ""), str(user.get("department_id") or ""))
    return DepartmentScope(allowed)
