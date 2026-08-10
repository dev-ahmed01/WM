"""Snowflake SQL Persistence layer for Operational Workflow Definitions (OWD).

Handles transactional persistence and retrieval of OWD state graphs, atomic steps,
transitions, rules, evidence specs, and semantic search metadata in Snowflake.
"""

import json
from datetime import datetime
from typing import Optional, Dict, Any, List
from app.core.database import get_snowflake_connection
from app.exceptions.custom_exceptions import DatabaseException


class OWDRepository:
    """Persistence and query repository for KNOWLEDGE_STUDIO and WORKMATE_COPILOT OWD structures."""

    @staticmethod
    def get_initial_state(workflow_version_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves initial state node for a workflow version."""
        query = """
            SELECT id, workflow_version_id, state_key, state_type, title, description, is_initial, is_terminal, ordinal_index
            FROM KNOWLEDGE_STUDIO.workflow_states
            WHERE workflow_version_id = %s AND is_initial = TRUE
            ORDER BY ordinal_index ASC
            LIMIT 1
        """
        try:
            with get_snowflake_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(query, (workflow_version_id,))
                    row = cur.fetchone()
                    if not row:
                        return None
                    cols = [c[0].lower() for c in cur.description]
                    return dict(zip(cols, row))
        except Exception as e:
            raise DatabaseException(message=f"Failed to fetch initial state for version {workflow_version_id}: {str(e)}")

    @staticmethod
    def get_state_by_id(state_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves state record by ID."""
        query = """
            SELECT id, workflow_version_id, state_key, state_type, title, description, is_initial, is_terminal, ordinal_index
            FROM KNOWLEDGE_STUDIO.workflow_states
            WHERE id = %s
        """
        try:
            with get_snowflake_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(query, (state_id,))
                    row = cur.fetchone()
                    if not row:
                        return None
                    cols = [c[0].lower() for c in cur.description]
                    return dict(zip(cols, row))
        except Exception as e:
            raise DatabaseException(message=f"Failed to fetch state {state_id}: {str(e)}")

    @staticmethod
    def get_steps_for_state(state_id: str) -> List[Dict[str, Any]]:
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
                    cols = [c[0].lower() for c in cur.description]
                    return [dict(zip(cols, r)) for r in rows]
        except Exception as e:
            raise DatabaseException(message=f"Failed to fetch steps for state {state_id}: {str(e)}")

    @staticmethod
    def get_next_state_transition(from_state_id: str, context: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """Evaluates graph edges and returns the matching next workflow state."""
        query = """
            SELECT t.id, t.from_state_id, t.to_state_id, t.condition_type, t.condition_expression, t.priority,
                   s.state_key, s.title, s.is_terminal
            FROM KNOWLEDGE_STUDIO.workflow_transitions t
            JOIN KNOWLEDGE_STUDIO.workflow_states s ON t.to_state_id = s.id
            WHERE t.from_state_id = %s
            ORDER BY t.priority ASC
            LIMIT 1
        """
        try:
            with get_snowflake_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(query, (from_state_id,))
                    row = cur.fetchone()
                    if not row:
                        return None
                    cols = [c[0].lower() for c in cur.description]
                    return dict(zip(cols, row))
        except Exception as e:
            raise DatabaseException(message=f"Failed to evaluate transition from state {from_state_id}: {str(e)}")

    @staticmethod
    def record_analytics_event(
        session_id: str,
        workflow_version_id: str,
        event_type: str,
        state_id: Optional[str] = None,
        step_id: Optional[str] = None,
        duration_ms: Optional[int] = None,
        payload: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Logs execution telemetry event into INTELLIGENCE_HUB.workflow_analytics_events."""
        event_id = f"evt_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{session_id[:8]}"
        payload_json = json.dumps(payload or {})
        query = """
            INSERT INTO INTELLIGENCE_HUB.workflow_analytics_events (
                id, session_id, workflow_version_id, state_id, step_id, event_type, duration_ms, event_payload, created_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, PARSE_JSON(%s), CURRENT_TIMESTAMP())
        """
        try:
            with get_snowflake_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        query,
                        (event_id, session_id, workflow_version_id, state_id, step_id, event_type, duration_ms, payload_json),
                    )
                    return True
        except Exception as e:
            # Telemetry logging should be resilient and non-blocking
            return False
