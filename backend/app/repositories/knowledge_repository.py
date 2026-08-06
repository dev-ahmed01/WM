"""Repository managing Snowflake SQL operations for OWD workflows, versions, states, and steps."""

import logging
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, Tuple
from app.core.config import settings
from app.core.database import get_snowflake_connection
from app.exceptions import WorkMateException

logger = logging.getLogger("workmate.knowledge_repository")


class KnowledgeRepository:
    """Handles read and update queries for KNOWLEDGE_STUDIO workflows, workflow_versions, workflow_states, and workflow_steps tables in Snowflake."""

    @staticmethod
    def get_next_version_number(knowledge_item_id: str) -> int:
        query = "SELECT COALESCE(MAX(version_number), 0) FROM KNOWLEDGE_STUDIO.workflow_versions WHERE workflow_id = %s"
        try:
            with get_snowflake_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(query, (knowledge_item_id,))
                    row = cur.fetchone()
                    if row and row[0] is not None:
                        return int(row[0]) + 1
                    return 1
        except Exception as exc:
            raise WorkMateException(message=f"Failed to calculate next version number: {str(exc)}") from exc

    @staticmethod
    def department_exists(department_id: str) -> bool:
        query = "SELECT 1 FROM SECURITY.departments WHERE id = %s AND is_active = TRUE LIMIT 1"
        try:
            with get_snowflake_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(query, (department_id,))
                    return cur.fetchone() is not None
        except Exception as exc:
            raise WorkMateException(message=f"Failed to validate department: {str(exc)}") from exc

    @staticmethod
    def list_departments() -> List[Dict[str, str]]:
        query = "SELECT id, name FROM SECURITY.departments WHERE is_active = TRUE ORDER BY name"
        try:
            with get_snowflake_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(query)
                    return [{"id": row[0], "name": row[1]} for row in cur.fetchall()]
        except Exception as exc:
            raise WorkMateException(message=f"Failed to list departments: {str(exc)}") from exc

    @staticmethod
    def get_version_by_id(version_id: str) -> Optional[Dict[str, Any]]:
        query = """
            SELECT id, workflow_id, version_number, semantic_version, stage_file_uri, ast_hash, status, created_at, published_at
            FROM KNOWLEDGE_STUDIO.workflow_versions
            WHERE id = %s
            LIMIT 1
        """
        try:
            with get_snowflake_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(query, (version_id,))
                    row = cur.fetchone()
                    if not row:
                        return None
                    return {
                        "id": row[0],
                        "knowledge_item_id": row[1],
                        "workflow_id": row[1],
                        "version_number": row[2],
                        "semantic_version": row[3],
                        "stage_file_uri": row[4],
                        "ast_hash": row[5],
                        "status": row[6],
                        "created_at": str(row[7]),
                        "published_at": str(row[8]) if row[8] else None,
                    }
        except Exception as exc:
            raise WorkMateException(message=f"Failed to fetch version by ID: {str(exc)}") from exc

    @staticmethod
    def get_item_by_id(item_id: str) -> Optional[Dict[str, Any]]:
        query = """
            SELECT id, workflow_code, title, description, department_id, category, created_by, created_at, updated_at
            FROM KNOWLEDGE_STUDIO.workflows
            WHERE id = %s OR workflow_code = %s
            LIMIT 1
        """
        try:
            with get_snowflake_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(query, (item_id, item_id))
                    row = cur.fetchone()
                    if not row:
                        return None
                    return {
                        "id": row[0],
                        "workflow_code": row[1],
                        "title": row[2],
                        "description": row[3],
                        "department_id": row[4],
                        "category": row[5],
                        "created_by": row[6],
                        "created_at": str(row[7]),
                        "updated_at": str(row[8]) if row[8] else str(row[7]),
                    }
        except Exception as exc:
            raise WorkMateException(message=f"Failed to fetch workflow item: {str(exc)}") from exc

    @staticmethod
    def get_latest_version(knowledge_item_id: str) -> Optional[Dict[str, Any]]:
        query = """
            SELECT id, workflow_id, version_number, semantic_version, stage_file_uri, ast_hash, status, created_at, published_at
            FROM KNOWLEDGE_STUDIO.workflow_versions
            WHERE workflow_id = %s
            ORDER BY version_number DESC
            LIMIT 1
        """
        try:
            with get_snowflake_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(query, (knowledge_item_id,))
                    row = cur.fetchone()
                    if not row:
                        return None
                    return {
                        "id": row[0],
                        "knowledge_item_id": row[1],
                        "workflow_id": row[1],
                        "version_number": row[2],
                        "semantic_version": row[3],
                        "stage_file_uri": row[4],
                        "ast_hash": row[5],
                        "status": row[6],
                        "created_at": str(row[7]),
                        "published_at": str(row[8]) if row[8] else None,
                    }
        except Exception as exc:
            raise WorkMateException(message=f"Failed to fetch latest version: {str(exc)}") from exc

    @staticmethod
    def get_published_version(knowledge_item_id: str) -> Optional[Dict[str, Any]]:
        query = """
            SELECT id, workflow_id, version_number, semantic_version, stage_file_uri, ast_hash, status, created_at, published_at
            FROM KNOWLEDGE_STUDIO.workflow_versions
            WHERE workflow_id = %s AND LOWER(status) = 'published'
            ORDER BY version_number DESC
            LIMIT 1
        """
        try:
            with get_snowflake_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(query, (knowledge_item_id,))
                    row = cur.fetchone()
                    if not row:
                        return None
                    return {
                        "id": row[0],
                        "knowledge_item_id": row[1],
                        "workflow_id": row[1],
                        "version_number": row[2],
                        "semantic_version": row[3],
                        "stage_file_uri": row[4],
                        "ast_hash": row[5],
                        "status": row[6],
                        "created_at": str(row[7]),
                        "published_at": str(row[8]) if row[8] else None,
                    }
        except Exception as exc:
            raise WorkMateException(message=f"Failed to fetch published version: {str(exc)}") from exc

    @staticmethod
    def get_version_history(knowledge_item_id: str) -> List[Dict[str, Any]]:
        query = """
            SELECT id, workflow_id, version_number, semantic_version, stage_file_uri, ast_hash, status, created_at, published_at
            FROM KNOWLEDGE_STUDIO.workflow_versions
            WHERE workflow_id = %s
            ORDER BY version_number DESC
        """
        try:
            with get_snowflake_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(query, (knowledge_item_id,))
                    rows = cur.fetchall()
                    return [
                        {
                            "id": r[0],
                            "knowledge_item_id": r[1],
                            "workflow_id": r[1],
                            "version_number": r[2],
                            "semantic_version": r[3],
                            "stage_file_uri": r[4],
                            "ast_hash": r[5],
                            "status": r[6],
                            "created_at": str(r[7]),
                            "published_at": str(r[8]) if r[8] else None,
                        }
                        for r in rows
                    ]
        except Exception as exc:
            raise WorkMateException(message=f"Failed to fetch version history: {str(exc)}") from exc

    @staticmethod
    def list_items(
        department_id: Optional[str] = None,
        status_filter: Optional[str] = None,
        page: int = 1,
        limit: int = 20,
    ) -> Tuple[List[Dict[str, Any]], int]:
        offset = (page - 1) * limit
        where_clauses = []
        params = []

        if department_id:
            where_clauses.append("w.department_id = %s")
            params.append(department_id)

        if status_filter:
            where_clauses.append("wv.status = %s")
            params.append(status_filter)

        where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

        query = f"""
            SELECT DISTINCT w.id, w.workflow_code, w.title, w.description, w.department_id, w.category, w.created_by, w.created_at
            FROM KNOWLEDGE_STUDIO.workflows w
            LEFT JOIN KNOWLEDGE_STUDIO.workflow_versions wv ON w.id = wv.workflow_id
            {where_sql}
            ORDER BY w.created_at DESC
            LIMIT %s OFFSET %s
        """
        count_query = f"""
            SELECT COUNT(DISTINCT w.id)
            FROM KNOWLEDGE_STUDIO.workflows w
            LEFT JOIN KNOWLEDGE_STUDIO.workflow_versions wv ON w.id = wv.workflow_id
            {where_sql}
        """
        exec_params = list(params) + [limit, offset]

        try:
            with get_snowflake_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(query, exec_params)
                    rows = cur.fetchall()

                    cur.execute(count_query, params)
                    total_count = cur.fetchone()[0]

                    items = [
                        {
                            "id": r[0],
                            "workflow_code": r[1],
                            "title": r[2],
                            "description": r[3],
                            "department_id": r[4],
                            "category": r[5],
                            "created_by": r[6],
                            "created_at": str(r[7]),
                        }
                        for r in rows
                    ]
                    return items, total_count
        except Exception as exc:
            raise WorkMateException(message=f"Failed to list workflow items: {str(exc)}") from exc

    @staticmethod
    def update_item_metadata(
        item_id: str,
        title: Optional[str] = None,
        department_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        updates = []
        params = []

        if title is not None:
            updates.append("title = %s")
            params.append(title)
        if department_id is not None:
            updates.append("department_id = %s")
            params.append(department_id)

        if not updates:
            return KnowledgeRepository.get_item_by_id(item_id)

        updates.append("updated_at = CURRENT_TIMESTAMP()")
        params.append(item_id)
        query = f"UPDATE KNOWLEDGE_STUDIO.workflows SET {', '.join(updates)} WHERE id = %s"

        try:
            with get_snowflake_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(query, params)
            return KnowledgeRepository.get_item_by_id(item_id)
        except Exception as exc:
            raise WorkMateException(message=f"Failed to update workflow metadata: {str(exc)}") from exc

    @staticmethod
    def update_version_status(version_id: str, status: str) -> bool:
        now = datetime.now(timezone.utc)
        published_at_clause = ", published_at = CURRENT_TIMESTAMP()" if status.lower() == "published" else ""
        query = f"UPDATE KNOWLEDGE_STUDIO.workflow_versions SET status = %s{published_at_clause} WHERE id = %s"

        try:
            with get_snowflake_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(query, (status, version_id))
                    return cur.rowcount > 0
        except Exception as exc:
            raise WorkMateException(message=f"Failed to update version status: {str(exc)}") from exc

    @staticmethod
    def soft_delete_item(item_id: str) -> bool:
        query = "UPDATE KNOWLEDGE_STUDIO.workflow_versions SET status = 'archived' WHERE workflow_id = %s"
        try:
            with get_snowflake_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(query, (item_id,))
                    return True
        except Exception as exc:
            raise WorkMateException(message=f"Failed to soft-delete workflow item: {str(exc)}") from exc

    @staticmethod
    def get_workflow_states(version_id: str) -> List[Dict[str, Any]]:
        """Retrieves state machine nodes for a workflow version."""
        query = """
            SELECT id, workflow_version_id, state_key, state_type, title, description, is_initial, is_terminal, ordinal_index
            FROM KNOWLEDGE_STUDIO.workflow_states
            WHERE workflow_version_id = %s
            ORDER BY ordinal_index ASC
        """
        try:
            with get_snowflake_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(query, (version_id,))
                    rows = cur.fetchall()
                    return [
                        {
                            "id": r[0],
                            "workflow_version_id": r[1],
                            "state_key": r[2],
                            "state_type": r[3],
                            "title": r[4],
                            "description": r[5],
                            "is_initial": r[6],
                            "is_terminal": r[7],
                            "ordinal_index": r[8],
                        }
                        for r in rows
                    ]
        except Exception as exc:
            raise WorkMateException(message=f"Failed to fetch workflow states: {str(exc)}") from exc

    @staticmethod
    def get_workflow_steps(state_id: str) -> List[Dict[str, Any]]:
        """Retrieves atomic steps for a given workflow state."""
        query = """
            SELECT id, state_id, step_code, instruction, ai_guidance_prompt, expected_output_type, is_mandatory, ordinal_index
            FROM KNOWLEDGE_STUDIO.workflow_steps
            WHERE state_id = %s
            ORDER BY ordinal_index ASC
        """
        try:
            with get_snowflake_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(query, (state_id,))
                    rows = cur.fetchall()
                    return [
                        {
                            "id": r[0],
                            "state_id": r[1],
                            "step_code": r[2],
                            "instruction": r[3],
                            "ai_guidance_prompt": r[4],
                            "expected_output_type": r[5],
                            "is_mandatory": r[6],
                            "ordinal_index": r[7],
                        }
                        for r in rows
                    ]
        except Exception as exc:
            raise WorkMateException(message=f"Failed to fetch workflow steps: {str(exc)}") from exc
