# Snowflake SQL Persistence layer for Escalations

import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any
from app.core.database import get_snowflake_connection
from app.exceptions.custom_exceptions import DatabaseException

class EscalationRepository:
    """Handles CRUD operations on the Snowflake 'escalations' table."""

    @staticmethod
    def create(conversation_message_id: str, reason: str) -> str:
        escalation_id = f"esc_{uuid.uuid4().hex[:12]}"
        now = datetime.utcnow()
        query = """
            INSERT INTO escalations (
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
        now = datetime.utcnow()
        if notified_at:
            query = """
                UPDATE escalations
                SET status = %s, notified_at = %s, updated_at = %s
                WHERE id = %s
            """
            params = (status, notified_at, now, escalation_id)
        else:
            query = """
                UPDATE escalations
                SET status = %s, updated_at = %s
                WHERE id = %s
            """
            params = (status, now, escalation_id)

        try:
            with get_snowflake_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(query, params)
                    return cur.rowcount > 0
        except Exception as e:
            raise DatabaseException(message=f"Failed to update escalation status: {str(e)}")

    @staticmethod
    def resolve(escalation_id: str, resolution_note: str) -> bool:
        now = datetime.utcnow()
        query = """
            UPDATE escalations
            SET status = 'resolved', resolution_note = %s, resolved_at = %s, updated_at = %s
            WHERE id = %s
        """
        try:
            with get_snowflake_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(query, (resolution_note, now, now, escalation_id))
                    return cur.rowcount > 0
        except Exception as e:
            raise DatabaseException(message=f"Failed to resolve escalation: {str(e)}")

    @staticmethod
    def list_all(limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
        query = """
            SELECT id, conversation_message_id, reason, status, notified_at, resolved_at, resolution_note, created_at, updated_at
            FROM escalations
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
