# Snowflake SQL Persistence layer for Workflow Sessions

import uuid
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from app.core.database import get_snowflake_connection
from app.exceptions.custom_exceptions import DatabaseException

class WorkflowSessionRepository:
    """Handles persistence for workflow_sessions in Snowflake."""

    @staticmethod
    def get_active_by_conversation(conversation_id: str) -> Optional[Dict[str, Any]]:
        query = """
            SELECT id, conversation_id, workflow_version_id, current_step, status,
                   abandon_reason, started_at AS created_at, updated_at
            FROM WORKMATE_COPILOT.workflow_sessions
            WHERE conversation_id = %s AND status = 'active'
            ORDER BY started_at DESC
            LIMIT 1
        """
        try:
            with get_snowflake_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(query, (conversation_id,))
                    row = cur.fetchone()
                    if not row:
                        return None
                    columns = [col[0].lower() for col in cur.description]
                    return dict(zip(columns, row))
        except Exception as e:
            raise DatabaseException(message=f"Failed to query active workflow session: {str(e)}")

    @staticmethod
    def get_by_id(session_id: str) -> Optional[Dict[str, Any]]:
        query = """
            SELECT id, conversation_id, workflow_version_id, current_step, status,
                   abandon_reason, started_at AS created_at, updated_at
            FROM WORKMATE_COPILOT.workflow_sessions
            WHERE id = %s
        """
        try:
            with get_snowflake_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(query, (session_id,))
                    row = cur.fetchone()
                    if not row:
                        return None
                    columns = [col[0].lower() for col in cur.description]
                    return dict(zip(columns, row))
        except Exception as e:
            raise DatabaseException(message=f"Failed to get workflow session {session_id}: {str(e)}")

    @staticmethod
    def create(conversation_id: str, workflow_version_id: str, current_state_id: str) -> str:
        session_id = f"sess_{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc)
        query = """
            INSERT INTO WORKMATE_COPILOT.workflow_sessions (
                id, conversation_id, workflow_version_id, current_state_id,
                user_id, current_step, status, started_at, updated_at
            )
            SELECT %s, %s, %s, %s, c.user_id, 0, 'active', %s, %s
            FROM WORKMATE_COPILOT.conversations c
            WHERE c.id = %s
        """
        try:
            with get_snowflake_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        query,
                        (
                            session_id,
                            conversation_id,
                            workflow_version_id,
                            current_state_id,
                            now,
                            now,
                            conversation_id,
                        ),
                    )
                    if cur.rowcount != 1:
                        raise DatabaseException(message="Conversation was not found for workflow session.")
            return session_id
        except Exception as e:
            raise DatabaseException(message=f"Failed to create workflow session: {str(e)}")

    @staticmethod
    def update_step_and_status(session_id: str, current_step: int, status: str) -> bool:
        now = datetime.now(timezone.utc)
        query = """
            UPDATE WORKMATE_COPILOT.workflow_sessions
            SET current_step = %s, status = %s, updated_at = %s
            WHERE id = %s
        """
        try:
            with get_snowflake_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(query, (current_step, status, now, session_id))
                    return cur.rowcount > 0
        except Exception as e:
            raise DatabaseException(message=f"Failed to update workflow session step: {str(e)}")

    @staticmethod
    def update_status(session_id: str, status: str, abandon_reason: Optional[str] = None) -> bool:
        now = datetime.now(timezone.utc)
        if abandon_reason:
            query = """
                UPDATE WORKMATE_COPILOT.workflow_sessions
                SET status = %s, abandon_reason = %s, updated_at = %s
                WHERE id = %s
            """
            params = (status, abandon_reason, now, session_id)
        else:
            query = """
                UPDATE WORKMATE_COPILOT.workflow_sessions
                SET status = %s, updated_at = %s
                WHERE id = %s
            """
            params = (status, now, session_id)

        try:
            with get_snowflake_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(query, params)
                    return cur.rowcount > 0
        except Exception as e:
            raise DatabaseException(message=f"Failed to update session status: {str(e)}")
