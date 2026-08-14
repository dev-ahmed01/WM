"""Persistent, department-scoped learning from confirmed Copilot SOP resolutions."""

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.core.database import get_snowflake_connection
from app.exceptions.custom_exceptions import DatabaseException

logger = logging.getLogger("workmate.query_resolution_repository")


class QueryResolutionRepository:
    """Store resolution attempts and expose only confirmed mappings for reuse."""

    @staticmethod
    def create_pending(
        *,
        department_id: str,
        original_query: str,
        normalized_query: str,
        original_language: str,
        translated_query: str,
        workflow_version_id: str,
        workflow_code: str,
        conversation_id: str,
        source_message_id: str,
        resolved_by: str,
    ) -> str:
        resolution_id = f"qres_{uuid.uuid4().hex[:16]}"
        now = datetime.now(timezone.utc)
        query = """
            INSERT INTO WORKMATE_COPILOT.query_resolution_memory (
                id, department_id, original_query, normalized_query,
                original_language, translated_query, workflow_version_id,
                workflow_code, resolution_status, source_conversation_id,
                source_message_id, resolved_by, hit_count, created_at, updated_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'PENDING', %s, %s, %s, 0, %s, %s)
        """
        try:
            with get_snowflake_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        query,
                        (
                            resolution_id, department_id, original_query,
                            normalized_query, original_language, translated_query,
                            workflow_version_id, workflow_code, conversation_id,
                            source_message_id, resolved_by, now, now,
                        ),
                    )
            return resolution_id
        except Exception as exc:
            raise DatabaseException(message=f"Failed to persist query resolution: {exc}") from exc

    @staticmethod
    def set_status(resolution_id: str, status: str) -> bool:
        if status not in {"CONFIRMED", "REJECTED"}:
            raise ValueError("Unsupported query resolution status")
        try:
            with get_snowflake_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        UPDATE WORKMATE_COPILOT.query_resolution_memory
                        SET resolution_status = %s, updated_at = %s
                        WHERE id = %s AND resolution_status = 'PENDING'
                        """,
                        (status, datetime.now(timezone.utc), resolution_id),
                    )
                    return cur.rowcount == 1
        except Exception as exc:
            raise DatabaseException(message=f"Failed to update query resolution: {exc}") from exc

    @staticmethod
    def list_confirmed(department_id: str, limit: int = 250) -> List[Dict[str, Any]]:
        query = """
            SELECT id, normalized_query, original_query, translated_query,
                   workflow_version_id, workflow_code, hit_count, updated_at
            FROM WORKMATE_COPILOT.query_resolution_memory
            WHERE department_id = %s AND resolution_status = 'CONFIRMED'
            QUALIFY ROW_NUMBER() OVER (
                PARTITION BY normalized_query, workflow_version_id
                ORDER BY updated_at DESC
            ) = 1
            ORDER BY hit_count DESC, updated_at DESC
            LIMIT %s
        """
        try:
            with get_snowflake_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(query, (department_id, limit))
                    columns = [column[0].lower() for column in cur.description]
                    return [dict(zip(columns, row)) for row in cur.fetchall()]
        except Exception as exc:
            raise DatabaseException(message=f"Failed to load query resolutions: {exc}") from exc

    @staticmethod
    def record_hit(resolution_id: str) -> None:
        try:
            with get_snowflake_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        UPDATE WORKMATE_COPILOT.query_resolution_memory
                        SET hit_count = hit_count + 1, last_used_at = %s, updated_at = %s
                        WHERE id = %s AND resolution_status = 'CONFIRMED'
                        """,
                        (datetime.now(timezone.utc), datetime.now(timezone.utc), resolution_id),
                    )
        except Exception:
            logger.exception("Failed to record query resolution hit id=%s", resolution_id)
