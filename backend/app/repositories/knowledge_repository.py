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
    def get_upload_context(department_id: str, knowledge_item_id: str) -> tuple[bool, int]:
        """Validate department and allocate a version with one Snowflake round-trip."""
        query = """
            SELECT
                EXISTS(
                    SELECT 1 FROM SECURITY.departments
                    WHERE id = %s AND COALESCE(is_active, TRUE) = TRUE
                ),
                COALESCE((
                    SELECT MAX(version_number)
                    FROM KNOWLEDGE_STUDIO.workflow_versions
                    WHERE workflow_id = %s
                ), 0) + 1
        """
        try:
            with get_snowflake_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(query, (department_id, knowledge_item_id))
                    row = cur.fetchone()
                    if not row:
                        raise WorkMateException(message="Snowflake returned no upload context.")
                    return bool(row[0]), int(row[1])
        except WorkMateException:
            raise
        except Exception as exc:
            raise WorkMateException(
                message=f"Failed to prepare SOP upload: {str(exc)}"
            ) from exc

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
        query = """
            SELECT 1 FROM SECURITY.departments
            WHERE id = %s AND COALESCE(is_active, TRUE) = TRUE
            LIMIT 1
        """
        try:
            with get_snowflake_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(query, (department_id,))
                    return cur.fetchone() is not None
        except Exception as exc:
            raise WorkMateException(message=f"Failed to validate department: {str(exc)}") from exc

    @staticmethod
    def list_departments() -> List[Dict[str, str]]:
        query = """
            SELECT id, name FROM SECURITY.departments
            WHERE COALESCE(is_active, TRUE) = TRUE
            ORDER BY name, id
        """
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
    def list_published_catalog(department_id: str) -> List[Dict[str, Any]]:
        """Return executable SOPs authorized for the caller's operational scope."""
        query = """
            SELECT workflow_id, workflow_code, title, description, department_id,
                   category, workflow_version_id, version_number
            FROM (
                SELECT w.id AS workflow_id, w.workflow_code, w.title,
                       w.description, w.department_id, w.category,
                       wv.id AS workflow_version_id, wv.version_number,
                       ROW_NUMBER() OVER (
                           PARTITION BY w.id
                           ORDER BY wv.version_number DESC, wv.published_at DESC
                       ) AS published_rank
                FROM KNOWLEDGE_STUDIO.workflows w
                JOIN KNOWLEDGE_STUDIO.workflow_versions wv
                  ON wv.workflow_id = w.id
                 AND LOWER(wv.status) = 'published'
                WHERE w.department_id = %s
                   OR LEFT(w.workflow_code, 3) = 'WH_'
            )
            WHERE published_rank = 1
            ORDER BY LOWER(title), LOWER(workflow_code)
        """
        try:
            with get_snowflake_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(query, (department_id,))
                    columns = [column[0].lower() for column in cur.description]
                    return [dict(zip(columns, row)) for row in cur.fetchall()]
        except Exception as exc:
            raise WorkMateException(
                message=f"Failed to list the published workflow catalog: {exc}"
            ) from exc

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
                    count_row = cur.fetchone()
                    total_count = int(count_row[0]) if count_row else 0

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
                    cur.execute("BEGIN")
                    try:
                        cur.execute(query, params)
                        if cur.rowcount != 1:
                            cur.execute("ROLLBACK")
                            return None
                        if department_id is not None:
                            cur.execute(
                                """
                                UPDATE KNOWLEDGE_STUDIO.workflow_search_metadata
                                SET department_id = %s
                                WHERE workflow_version_id IN (
                                    SELECT id FROM KNOWLEDGE_STUDIO.workflow_versions
                                    WHERE workflow_id = %s
                                )
                                """,
                                (department_id, item_id),
                            )
                            cur.execute(
                                """
                                UPDATE KNOWLEDGE_STUDIO.workflow_role_permissions
                                SET department_id = %s
                                WHERE workflow_version_id IN (
                                    SELECT id FROM KNOWLEDGE_STUDIO.workflow_versions
                                    WHERE workflow_id = %s
                                )
                                """,
                                (department_id, item_id),
                            )
                        cur.execute("COMMIT")
                    except Exception:
                        cur.execute("ROLLBACK")
                        raise
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
                    return (cur.rowcount or 0) > 0
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
    def permanently_delete_item(item_id: str) -> Dict[str, Any]:
        """Delete one SOP and its workflow-dependent records in a single transaction.

        Conversations and conversation messages are intentionally retained. Their
        rendered text and embedded citations remain available as historical audit
        context, while executable workflow sessions and graph data are removed.
        """
        version_filter = (
            "SELECT id FROM KNOWLEDGE_STUDIO.workflow_versions WHERE workflow_id = %s"
        )
        state_filter = f"""
            SELECT id FROM KNOWLEDGE_STUDIO.workflow_states
            WHERE workflow_version_id IN ({version_filter})
        """
        step_filter = f"""
            SELECT id FROM KNOWLEDGE_STUDIO.workflow_steps
            WHERE state_id IN ({state_filter})
        """
        session_filter = f"""
            SELECT id FROM WORKMATE_COPILOT.workflow_sessions
            WHERE workflow_version_id IN ({version_filter})
        """
        execution_filter = f"""
            SELECT id FROM WORKMATE_COPILOT.workflow_step_executions
            WHERE session_id IN ({session_filter})
        """

        statements: List[Tuple[str, str, Tuple[Any, ...]]] = [
            (
                "workflow_evidence_submissions",
                f"DELETE FROM WORKMATE_COPILOT.workflow_evidence_submissions WHERE step_execution_id IN ({execution_filter})",
                (item_id,),
            ),
            (
                "escalation_records",
                f"DELETE FROM WORKMATE_COPILOT.escalation_records WHERE session_id IN ({session_filter})",
                (item_id,),
            ),
            (
                "workflow_step_executions",
                f"DELETE FROM WORKMATE_COPILOT.workflow_step_executions WHERE session_id IN ({session_filter})",
                (item_id,),
            ),
            (
                "workflow_analytics_events",
                f"DELETE FROM INTELLIGENCE_HUB.workflow_analytics_events WHERE workflow_version_id IN ({version_filter})",
                (item_id,),
            ),
            (
                "analytics_events",
                f"DELETE FROM INTELLIGENCE_HUB.analytics_events WHERE workflow_version_id IN ({version_filter})",
                (item_id,),
            ),
            (
                "workflow_sessions",
                f"DELETE FROM WORKMATE_COPILOT.workflow_sessions WHERE workflow_version_id IN ({version_filter})",
                (item_id,),
            ),
            (
                "knowledge_document_lineage",
                f"DELETE FROM KNOWLEDGE_STUDIO.knowledge_document_lineage WHERE workflow_version_id IN ({version_filter})",
                (item_id,),
            ),
            (
                "knowledge_document_chunks",
                f"DELETE FROM KNOWLEDGE_STUDIO.knowledge_document_chunks WHERE workflow_version_id IN ({version_filter})",
                (item_id,),
            ),
            (
                "knowledge_document_ai_metadata",
                f"DELETE FROM KNOWLEDGE_STUDIO.knowledge_document_ai_metadata WHERE workflow_version_id IN ({version_filter})",
                (item_id,),
            ),
            (
                "knowledge_document_contents",
                f"DELETE FROM KNOWLEDGE_STUDIO.knowledge_document_contents WHERE workflow_version_id IN ({version_filter})",
                (item_id,),
            ),
            (
                "knowledge_documents",
                "DELETE FROM KNOWLEDGE_STUDIO.knowledge_documents WHERE workflow_id = %s",
                (item_id,),
            ),
            (
                "workflow_evidence_specs",
                f"DELETE FROM KNOWLEDGE_STUDIO.workflow_evidence_specs WHERE step_id IN ({step_filter})",
                (item_id,),
            ),
            (
                "workflow_ai_conversation",
                f"DELETE FROM KNOWLEDGE_STUDIO.workflow_ai_conversation WHERE step_id IN ({step_filter})",
                (item_id,),
            ),
            (
                "workflow_decision_options",
                f"DELETE FROM KNOWLEDGE_STUDIO.workflow_decision_options WHERE state_id IN ({state_filter})",
                (item_id,),
            ),
            (
                "workflow_decisions",
                f"DELETE FROM KNOWLEDGE_STUDIO.workflow_decisions WHERE state_id IN ({state_filter})",
                (item_id,),
            ),
            (
                "workflow_transitions",
                f"DELETE FROM KNOWLEDGE_STUDIO.workflow_transitions WHERE from_state_id IN ({state_filter}) OR to_state_id IN ({state_filter})",
                (item_id, item_id),
            ),
            (
                "workflow_rules",
                f"DELETE FROM KNOWLEDGE_STUDIO.workflow_rules WHERE state_id IN ({state_filter})",
                (item_id,),
            ),
            (
                "workflow_escalation_policies",
                f"DELETE FROM KNOWLEDGE_STUDIO.workflow_escalation_policies WHERE state_id IN ({state_filter})",
                (item_id,),
            ),
            (
                "workflow_analytics",
                f"DELETE FROM KNOWLEDGE_STUDIO.workflow_analytics WHERE workflow_version_id IN ({version_filter})",
                (item_id,),
            ),
            (
                "workflow_relationships",
                f"DELETE FROM KNOWLEDGE_STUDIO.workflow_relationships WHERE workflow_version_id IN ({version_filter})",
                (item_id,),
            ),
            (
                "workflow_references",
                f"DELETE FROM KNOWLEDGE_STUDIO.workflow_references WHERE workflow_version_id IN ({version_filter})",
                (item_id,),
            ),
            (
                "workflow_role_permissions",
                f"DELETE FROM KNOWLEDGE_STUDIO.workflow_role_permissions WHERE workflow_version_id IN ({version_filter})",
                (item_id,),
            ),
            (
                "workflow_search_metadata",
                f"DELETE FROM KNOWLEDGE_STUDIO.workflow_search_metadata WHERE workflow_version_id IN ({version_filter})",
                (item_id,),
            ),
            (
                "workflow_steps",
                f"DELETE FROM KNOWLEDGE_STUDIO.workflow_steps WHERE state_id IN ({state_filter})",
                (item_id,),
            ),
            (
                "workflow_states",
                f"DELETE FROM KNOWLEDGE_STUDIO.workflow_states WHERE workflow_version_id IN ({version_filter})",
                (item_id,),
            ),
            (
                "workflow_versions",
                "DELETE FROM KNOWLEDGE_STUDIO.workflow_versions WHERE workflow_id = %s",
                (item_id,),
            ),
            (
                "workflows",
                "DELETE FROM KNOWLEDGE_STUDIO.workflows WHERE id = %s",
                (item_id,),
            ),
        ]

        try:
            with get_snowflake_connection() as conn:
                with conn.cursor() as cur:
                    deleted_counts: Dict[str, int] = {}
                    cur.execute("BEGIN")
                    try:
                        cur.execute(
                            "SELECT DISTINCT stage_file_uri FROM KNOWLEDGE_STUDIO.workflow_versions WHERE workflow_id = %s",
                            (item_id,),
                        )
                        stage_file_uris = [
                            str(row[0]) for row in cur.fetchall() if row[0]
                        ]
                        for label, statement, params in statements:
                            cur.execute(statement, params)
                            deleted_counts[label] = max(0, int(cur.rowcount or 0))
                        if deleted_counts.get("workflows") != 1:
                            raise WorkMateException(message=f"Workflow item '{item_id}' was not found.")
                        cur.execute("COMMIT")
                    except Exception:
                        cur.execute("ROLLBACK")
                        raise
                    return {
                        "deleted_counts": deleted_counts,
                        "stage_file_uris": stage_file_uris,
                    }
        except WorkMateException:
            raise
        except Exception as exc:
            raise WorkMateException(
                message=f"Failed to permanently delete workflow item: {str(exc)}"
            ) from exc

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
