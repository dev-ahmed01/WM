# Snowflake SQL Persistence layer for Escalations

import uuid
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from app.core.database import get_snowflake_connection
from app.exceptions.custom_exceptions import DatabaseException

class EscalationRepository:
    """Handles CRUD operations on WORKMATE_COPILOT.escalation_records."""

    @staticmethod
    def create(conversation_message_id: str, reason: str) -> str:
        escalation_id = f"esc_{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc)
        query = """
            INSERT INTO WORKMATE_COPILOT.escalation_records (
                id, conversation_message_id, reason, status, created_at, updated_at
            ) VALUES (%s, %s, %s, %s, %s, %s)
        """
        try:
            with get_snowflake_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(query, (escalation_id, conversation_message_id, reason, 'open', now, now))
            return escalation_id
        except Exception as e:
            raise DatabaseException(message=f"Failed to create escalation record: {str(e)}")

    @staticmethod
    def update_status(escalation_id: str, status: str, notified_at: Optional[datetime] = None) -> bool:
        now = datetime.now(timezone.utc)
        if notified_at:
            query = """
                UPDATE WORKMATE_COPILOT.escalation_records
                SET status = %s, notified_at = %s, updated_at = %s
                WHERE id = %s
            """
            params = (status, notified_at, now, escalation_id)
        else:
            query = """
                UPDATE WORKMATE_COPILOT.escalation_records
                SET status = %s, updated_at = %s
                WHERE id = %s
            """
            params = (status, now, escalation_id)

        try:
            with get_snowflake_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(query, params)
                    return (cur.rowcount or 0) > 0
        except Exception as e:
            raise DatabaseException(message=f"Failed to update escalation status: {str(e)}")

    @staticmethod
    def resolve(escalation_id: str, resolution_note: str) -> bool:
        now = datetime.now(timezone.utc)
        query = """
            UPDATE WORKMATE_COPILOT.escalation_records
            SET status = 'resolved', resolution_note = %s, resolved_at = %s, updated_at = %s
            WHERE id = %s
        """
        try:
            with get_snowflake_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(query, (resolution_note, now, now, escalation_id))
                    return (cur.rowcount or 0) > 0
        except Exception as e:
            raise DatabaseException(message=f"Failed to resolve escalation: {str(e)}")

    @staticmethod
    def list_all(limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
        query = """
            SELECT id, conversation_message_id, reason, status, notified_at, resolved_at, resolution_note, created_at, updated_at
            FROM WORKMATE_COPILOT.escalation_records
            ORDER BY created_at DESC
            LIMIT %s OFFSET %s
        """
        try:
            with get_snowflake_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(query, (limit, offset))
                    rows = cur.fetchall()
                    columns = [col[0].lower() for col in cur.description]
                    return [dict(zip(columns, row)) for row in rows]
        except Exception as e:
            raise DatabaseException(message=f"Failed to list escalations: {str(e)}")


_SCOPE_FROM = """
    FROM WORKMATE_COPILOT.escalation_records e
    LEFT JOIN WORKMATE_COPILOT.conversation_messages m ON m.id = e.conversation_message_id
    LEFT JOIN WORKMATE_COPILOT.workflow_sessions s ON s.id = e.session_id
    JOIN WORKMATE_COPILOT.conversations c ON c.id = COALESCE(m.conversation_id, s.conversation_id)
    JOIN SECURITY.departments d ON d.id = c.department_id
"""


class ScopedEscalationRepository:
    """Tenant-scoped escalation access.

    Admins see their organization; managers see their own department. An
    escalation not linked to any conversation is invisible (fail closed).
    """

    @staticmethod
    def _scope(organization_id: Optional[str], department_id: Optional[str]):
        if not organization_id:
            raise DatabaseException(message="Organization scope is required")
        clause, params = "d.organization_id = %s", [organization_id]
        if department_id:
            clause += " AND c.department_id = %s"
            params.append(department_id)
        return clause, params

    @staticmethod
    def list_scoped(organization_id: Optional[str], department_id: Optional[str],
                    limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
        clause, params = ScopedEscalationRepository._scope(organization_id, department_id)
        query = ("SELECT e.id, e.conversation_message_id, e.reason, e.status, e.notified_at, "
                 "e.resolved_at, e.resolution_note, e.created_at, e.updated_at "
                 f"{_SCOPE_FROM} WHERE {clause} ORDER BY e.created_at DESC LIMIT %s OFFSET %s")
        with get_snowflake_connection() as conn, conn.cursor() as cur:
            cur.execute(query, (*params, limit, offset))
            columns = [col[0].lower() for col in cur.description]
            return [dict(zip(columns, row)) for row in cur.fetchall()]

    @staticmethod
    def resolve_scoped(escalation_id: str, resolution_note: str,
                       organization_id: Optional[str], department_id: Optional[str]) -> bool:
        clause, params = ScopedEscalationRepository._scope(organization_id, department_id)
        now = datetime.now(timezone.utc)
        query = ("UPDATE WORKMATE_COPILOT.escalation_records SET status='resolved', resolution_note=%s, "
                 "resolved_at=%s, updated_at=%s WHERE id = %s AND id IN (SELECT e.id "
                 f"{_SCOPE_FROM} WHERE {clause})")
        with get_snowflake_connection() as conn, conn.cursor() as cur:
            cur.execute(query, (resolution_note, now, now, escalation_id, *params))
            return (cur.rowcount or 0) > 0
