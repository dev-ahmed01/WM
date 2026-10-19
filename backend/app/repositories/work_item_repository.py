"""Work queue repository: department-scoped manager creation and owner-only worker views.

Queue entries are not executable workflows. Completion and evidence transitions
are deliberately absent until the governed Phase 2 state engine is implemented.
"""
from __future__ import annotations

from uuid import uuid4
from app.core.database import get_postgres_connection


COLUMNS = ("id,department_id,created_by,assigned_to,external_reference,"
           "title,work_type,priority,instructions,status,created_at,updated_at")


def _rows(cursor):
    keys = [col.name.lower() for col in cursor.description]
    items = [dict(zip(keys, row)) for row in cursor.fetchall()]
    for item in items:
        for key in ("created_at", "updated_at"):
            if item.get(key) is not None:
                item[key] = item[key].isoformat()
    return items


class WorkItemRepository:
    @staticmethod
    def create(department: str, actor: str, title: str, work_type: str,
               priority: str, instructions: str, external_reference: str,
               assigned_to: str | None) -> dict | None:
        identifier = "wrk_" + uuid4().hex
        with get_postgres_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("BEGIN")
                try:
                    cur.execute("SELECT set_config('workmate.department_id',%s,true)",(department,))
                    # Caller-supplied assignee must be an active user in this department.
                    if assigned_to:
                        cur.execute("""SELECT 1 FROM security.users u
                                       JOIN security.user_roles ur ON ur.user_id=u.id
                                       JOIN security.roles r ON r.id=ur.role_id
                                       WHERE u.id=%s AND u.department_id=%s
                                         AND u.status='active' AND LOWER(r.name)='employee'""",
                                    (assigned_to,department))
                        if not cur.fetchone():
                            cur.execute("ROLLBACK")
                            return None
                    cur.execute("""
                      INSERT INTO workmate_copilot.work_items (
                        id,department_id,created_by,assigned_to,external_reference,
                        title,work_type,priority,instructions
                      ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                      RETURNING """ + COLUMNS,
                        (identifier,department,actor,assigned_to,
                         external_reference,title,work_type,priority,instructions))
                    item = _rows(cur)[0]
                    cur.execute("""
                      INSERT INTO workmate_copilot.work_item_events
                        (id,work_item_id,department_id,actor_id,action)
                      VALUES (%s,%s,%s,%s,'created')
                    """,(uuid4().hex,identifier,department,actor))
                    cur.execute("COMMIT")
                    return item
                except Exception:
                    cur.execute("ROLLBACK")
                    raise

    @staticmethod
    def list(department: str, actor: str, can_manage: bool, limit: int = 100) -> list[dict]:
        with get_postgres_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("BEGIN")
                try:
                    cur.execute("SELECT set_config('workmate.department_id',%s,true)",(department,))
                    cur.execute("""SELECT """ + COLUMNS + """
                      FROM workmate_copilot.work_items
                      WHERE department_id=%s AND (%s OR assigned_to=%s)
                      ORDER BY CASE priority WHEN 'high' THEN 0 ELSE 1 END,
                               created_at DESC LIMIT %s""",
                               (department,can_manage,actor,limit))
                    rows = _rows(cur)
                    cur.execute("COMMIT")
                    return rows
                except Exception:
                    cur.execute("ROLLBACK")
                    raise

    @staticmethod
    def get(department: str, actor: str, can_manage: bool, item_id: str) -> dict | None:
        with get_postgres_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("BEGIN")
                try:
                    cur.execute("SELECT set_config('workmate.department_id',%s,true)",(department,))
                    cur.execute("""SELECT """ + COLUMNS + """
                      FROM workmate_copilot.work_items
                      WHERE id=%s AND department_id=%s AND (%s OR assigned_to=%s)""",
                               (item_id,department,can_manage,actor))
                    rows = _rows(cur)
                    cur.execute("COMMIT")
                    return rows[0] if rows else None
                except Exception:
                    cur.execute("ROLLBACK")
                    raise

    @staticmethod
    def assignees(department: str) -> list[dict]:
        """Only active employees in the requesting manager's department."""
        with get_postgres_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("BEGIN")
                try:
                    cur.execute("SELECT set_config('workmate.department_id',%s,true)",(department,))
                    cur.execute("""
                      SELECT DISTINCT u.id, COALESCE(NULLIF(u.full_name,''),u.id) AS label
                      FROM security.users u
                      JOIN security.user_roles ur ON ur.user_id=u.id
                      JOIN security.roles r ON r.id=ur.role_id
                      WHERE u.department_id=%s AND u.status='active' AND LOWER(r.name)='employee'
                      ORDER BY label LIMIT 100
                    """,(department,))
                    values=[{"id":str(row[0]),"label":str(row[1])} for row in cur.fetchall()]
                    cur.execute("COMMIT")
                    return values
                except Exception:
                    cur.execute("ROLLBACK")
                    raise
