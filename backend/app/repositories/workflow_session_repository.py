"""Snowflake persistence for OWD workflow execution sessions."""

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from app.core.database import get_snowflake_connection
from app.exceptions.custom_exceptions import DatabaseException


_SESSION_COLUMNS = """
    id, conversation_id, workflow_version_id, current_state_id,
    previous_state_id, user_id, status, session_context,
    started_at, updated_at, completed_at
"""


class WorkflowSessionRepository:
    """Queries the schema defined by analytics/migrations/04_workmate_copilot.sql."""

    @staticmethod
    def _row(cur: Any, row: Any) -> Dict[str, Any]:
        data = dict(zip([column[0].lower() for column in cur.description], row))
        context = data.get("session_context")
        if isinstance(context, str):
            try:
                data["session_context"] = json.loads(context)
            except json.JSONDecodeError:
                data["session_context"] = {}
        elif not isinstance(context, dict):
            data["session_context"] = {}
        return data

    @staticmethod
    def get_active_by_conversation(conversation_id: str) -> Optional[Dict[str, Any]]:
        query = f"""
            SELECT {_SESSION_COLUMNS}
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
                    return WorkflowSessionRepository._row(cur, row) if row else None
        except Exception as exc:
            raise DatabaseException(message=f"Failed to query active workflow session: {exc}") from exc

    @staticmethod
    def get_current_by_conversation(conversation_id: str) -> Optional[Dict[str, Any]]:
        """Return the resumable session, including a paused session."""
        query = f"""
            SELECT {_SESSION_COLUMNS}
            FROM WORKMATE_COPILOT.workflow_sessions
            WHERE conversation_id = %s AND status IN ('active', 'paused')
            ORDER BY started_at DESC
            LIMIT 1
        """
        try:
            with get_snowflake_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(query, (conversation_id,))
                    row = cur.fetchone()
                    return WorkflowSessionRepository._row(cur, row) if row else None
        except Exception as exc:
            raise DatabaseException(message=f"Failed to query current workflow session: {exc}") from exc

    @staticmethod
    def get_by_id(session_id: str) -> Optional[Dict[str, Any]]:
        query = f"""
            SELECT {_SESSION_COLUMNS}
            FROM WORKMATE_COPILOT.workflow_sessions
            WHERE id = %s
        """
        try:
            with get_snowflake_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(query, (session_id,))
                    row = cur.fetchone()
                    return WorkflowSessionRepository._row(cur, row) if row else None
        except Exception as exc:
            raise DatabaseException(message=f"Failed to get workflow session {session_id}: {exc}") from exc

    @staticmethod
    def create(
        conversation_id: str,
        workflow_version_id: str,
        current_state_id: str,
        user_id: str,
        session_context: Optional[Dict[str, Any]] = None,
    ) -> str:
        session_id = f"sess_{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc)
        query = """
            INSERT INTO WORKMATE_COPILOT.workflow_sessions (
                id, conversation_id, workflow_version_id, current_state_id,
                user_id, status, session_context, started_at, updated_at
            ) SELECT %s, %s, %s, %s, %s, 'active', PARSE_JSON(%s), %s, %s
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
                            user_id,
                            json.dumps(session_context or {}),
                            now,
                            now,
                        ),
                    )
            return session_id
        except Exception as exc:
            raise DatabaseException(message=f"Failed to create workflow session: {exc}") from exc

    @staticmethod
    def apply_progress(
        session_id: str,
        expected_state_id: str,
        expected_updated_at: datetime,
        session_context: Dict[str, Any],
        *,
        step_id: Optional[str] = None,
        next_state_id: Optional[str] = None,
        new_status: str = "active",
    ) -> bool:
        """Atomically record a completed step and/or move the session graph cursor."""
        execution_id = f"exec_{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc)
        try:
            with get_snowflake_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("BEGIN")
                    try:
                        target_state_id = next_state_id or expected_state_id
                        completed_at = now if new_status == "completed" else None
                        cur.execute(
                            """
                            UPDATE WORKMATE_COPILOT.workflow_sessions
                            SET previous_state_id = IFF(%s <> current_state_id, current_state_id, previous_state_id),
                                current_state_id = %s,
                                status = %s,
                                session_context = PARSE_JSON(%s),
                                updated_at = %s,
                                completed_at = %s
                            WHERE id = %s
                              AND current_state_id = %s
                              AND status = 'active'
                              AND updated_at = %s
                            """,
                            (
                                target_state_id,
                                target_state_id,
                                new_status,
                                json.dumps(session_context),
                                now,
                                completed_at,
                                session_id,
                                expected_state_id,
                                expected_updated_at,
                            ),
                        )
                        if cur.rowcount != 1:
                            raise DatabaseException(
                                message="Workflow session changed concurrently or is no longer active."
                            )
                        if step_id:
                            cur.execute(
                                """
                                INSERT INTO WORKMATE_COPILOT.workflow_step_executions
                                    (id, session_id, step_id, status, input_payload, executed_at)
                                SELECT %s, %s, %s, 'PASSED', PARSE_JSON(%s), %s
                                """,
                                (execution_id, session_id, step_id, json.dumps(session_context), now),
                            )
                        cur.execute("COMMIT")
                    except Exception:
                        cur.execute("ROLLBACK")
                        raise
            return True
        except Exception as exc:
            if isinstance(exc, DatabaseException):
                raise
            raise DatabaseException(message=f"Failed to advance workflow session: {exc}") from exc

    @staticmethod
    def update_status(
        session_id: str,
        expected_status: str,
        new_status: str,
        session_context: Dict[str, Any],
    ) -> bool:
        now = datetime.now(timezone.utc)
        completed_at = now if new_status == "completed" else None
        query = """
            UPDATE WORKMATE_COPILOT.workflow_sessions
            SET status = %s,
                session_context = PARSE_JSON(%s),
                updated_at = %s,
                completed_at = COALESCE(%s, completed_at)
            WHERE id = %s AND status = %s
        """
        try:
            with get_snowflake_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        query,
                        (
                            new_status,
                            json.dumps(session_context),
                            now,
                            completed_at,
                            session_id,
                            expected_status,
                        ),
                    )
                    return cur.rowcount == 1
        except Exception as exc:
            raise DatabaseException(message=f"Failed to update session status: {exc}") from exc
