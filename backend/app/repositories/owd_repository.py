"""Snowflake SQL Persistence layer for Operational Workflow Definitions (OWD).

Handles transactional persistence and retrieval of OWD state graphs, atomic steps,
transitions, rules, evidence specs, and semantic search metadata in Snowflake.
"""

import json
import re
import uuid
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
    def get_step_by_ordinal(
        workflow_version_id: str, ordinal_index: int
    ) -> Optional[Dict[str, Any]]:
        """Return a persisted workflow step by its user-facing global number."""
        query = """
            SELECT st.id, st.state_id, st.step_code, st.instruction,
                   st.expected_output_type, st.is_mandatory, st.ordinal_index
            FROM KNOWLEDGE_STUDIO.workflow_steps st
            JOIN KNOWLEDGE_STUDIO.workflow_states ws ON ws.id = st.state_id
            WHERE ws.workflow_version_id = %s AND st.ordinal_index = %s
            LIMIT 1
        """
        try:
            with get_snowflake_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(query, (workflow_version_id, ordinal_index))
                    row = cur.fetchone()
                    if not row:
                        return None
                    return dict(zip([column[0].lower() for column in cur.description], row))
        except Exception as exc:
            raise DatabaseException(
                message=(
                    f"Failed to fetch step {ordinal_index} for workflow version "
                    f"{workflow_version_id}: {exc}"
                )
            ) from exc

    @staticmethod
    def get_last_step_ordinal(workflow_version_id: str) -> Optional[int]:
        """Return the highest persisted global step number in a workflow graph."""
        query = """
            SELECT MAX(st.ordinal_index)
            FROM KNOWLEDGE_STUDIO.workflow_steps st
            JOIN KNOWLEDGE_STUDIO.workflow_states ws ON ws.id = st.state_id
            WHERE ws.workflow_version_id = %s
        """
        try:
            with get_snowflake_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(query, (workflow_version_id,))
                    row = cur.fetchone()
                    return int(row[0]) if row and row[0] is not None else None
        except Exception as exc:
            raise DatabaseException(
                message=(
                    "Failed to fetch the final step number for workflow version "
                    f"{workflow_version_id}: {exc}"
                )
            ) from exc

    @staticmethod
    def get_decision_options(state_id: str) -> List[Dict[str, Any]]:
        """Return the persisted user-selectable edges for a decision state."""
        query = """
            SELECT option_code, option_label
            FROM KNOWLEDGE_STUDIO.workflow_decision_options
            WHERE state_id = %s
            ORDER BY option_code ASC
        """
        try:
            with get_snowflake_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(query, (state_id,))
                    columns = [column[0].lower() for column in cur.description]
                    return [dict(zip(columns, row)) for row in cur.fetchall()]
        except Exception as exc:
            raise DatabaseException(
                message=f"Failed to fetch decision options for state {state_id}: {exc}"
            ) from exc

    @staticmethod
    def get_next_state_transition(from_state_id: str, context: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """Return the first matching transition without evaluating arbitrary code."""
        query = """
            SELECT t.id, t.from_state_id, t.to_state_id, t.condition_type, t.condition_expression, t.priority,
                   s.state_key, s.title, s.is_terminal,
                   o.option_code, o.option_label
            FROM KNOWLEDGE_STUDIO.workflow_transitions t
            JOIN KNOWLEDGE_STUDIO.workflow_states s ON t.to_state_id = s.id
            LEFT JOIN KNOWLEDGE_STUDIO.workflow_decision_options o
              ON o.state_id = t.from_state_id
             AND o.target_state_id = t.to_state_id
             AND UPPER(o.option_code) = UPPER(t.condition_expression)
            WHERE t.from_state_id = %s
            ORDER BY t.priority ASC, t.id ASC
        """
        try:
            with get_snowflake_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(query, (from_state_id,))
                    cols = [c[0].lower() for c in cur.description]
                    transitions = [dict(zip(cols, row)) for row in cur.fetchall()]
            return OWDRepository._select_transition(transitions, context or {})
        except Exception as e:
            raise DatabaseException(message=f"Failed to evaluate transition from state {from_state_id}: {str(e)}")

    @staticmethod
    def _select_transition(
        transitions: List[Dict[str, Any]], context: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Evaluate the condition types declared by the persisted OWD graph."""
        fallback: Optional[Dict[str, Any]] = None
        selected_option = str(context.get("decision_option") or "").strip().casefold()
        rule_results = context.get("rule_results") or {}
        values = {**(context.get("values") or {}), **context}

        for transition in transitions:
            condition_type = str(transition.get("condition_type") or "ALWAYS").upper()
            expression = str(transition.get("condition_expression") or "").strip()
            if condition_type == "FALLBACK":
                fallback = fallback or transition
                continue
            if condition_type == "ALWAYS":
                return transition
            if condition_type == "DECISION_OPTION":
                choices = {
                    expression.casefold(),
                    str(transition.get("option_code") or "").casefold(),
                    str(transition.get("option_label") or "").casefold(),
                }
                if selected_option and selected_option in choices:
                    return transition
                continue
            if condition_type in {"RULE_PASS", "RULE_FAIL"}:
                result = rule_results.get(expression)
                if isinstance(result, bool) and result is (condition_type == "RULE_PASS"):
                    return transition
                continue
            if condition_type == "EXPRESSION" and OWDRepository._expression_matches(expression, values):
                return transition
        return fallback if context.get("use_fallback") is True else None

    @staticmethod
    def _expression_matches(expression: str, values: Dict[str, Any]) -> bool:
        """Support boolean keys and simple equality comparisons; never call eval()."""
        if expression in values and isinstance(values[expression], bool):
            return values[expression]
        match = re.fullmatch(
            r"([A-Za-z_][A-Za-z0-9_.-]*)\s*(==|!=)\s*['\"]?([^'\"]+)['\"]?",
            expression,
        )
        if not match:
            return False
        key, operator, expected = match.groups()
        if key not in values:
            return False
        is_equal = str(values[key]).casefold() == expected.strip().casefold()
        return is_equal if operator == "==" else not is_equal

    @staticmethod
    def get_next_pending_step(session_id: str, state_id: str) -> Optional[Dict[str, Any]]:
        query = """
            SELECT st.id, st.state_id, st.step_code, st.instruction,
                   st.expected_output_type, st.ordinal_index
            FROM KNOWLEDGE_STUDIO.workflow_steps st
            WHERE st.state_id = %s
              AND NOT EXISTS (
                  SELECT 1
                  FROM WORKMATE_COPILOT.workflow_step_executions ex
                  WHERE ex.session_id = %s
                    AND ex.step_id = st.id
                    AND ex.status IN ('PASSED', 'SKIPPED')
              )
            ORDER BY st.ordinal_index ASC, st.id ASC
            LIMIT 1
        """
        try:
            with get_snowflake_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(query, (state_id, session_id))
                    row = cur.fetchone()
                    if not row:
                        return None
                    return dict(zip([c[0].lower() for c in cur.description], row))
        except Exception as exc:
            raise DatabaseException(message=f"Failed to fetch pending workflow step: {exc}") from exc

    @staticmethod
    def count_pending_steps(session_id: str, state_id: str) -> int:
        query = """
            SELECT COUNT(*)
            FROM KNOWLEDGE_STUDIO.workflow_steps st
            WHERE st.state_id = %s
              AND NOT EXISTS (
                  SELECT 1
                  FROM WORKMATE_COPILOT.workflow_step_executions ex
                  WHERE ex.session_id = %s
                    AND ex.step_id = st.id
                    AND ex.status IN ('PASSED', 'SKIPPED')
              )
        """
        try:
            with get_snowflake_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(query, (state_id, session_id))
                    row = cur.fetchone()
                    return int(row[0]) if row else 0
        except Exception as exc:
            raise DatabaseException(message=f"Failed to count pending workflow steps: {exc}") from exc

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
        event_id = f"evt_{uuid.uuid4().hex[:20]}"
        payload_json = json.dumps(payload or {})
        query = """
            INSERT INTO INTELLIGENCE_HUB.workflow_analytics_events (
                id, session_id, workflow_version_id, state_id, step_id, event_type, duration_ms, event_payload, created_at
            ) SELECT %s, %s, %s, %s, %s, %s, %s, PARSE_JSON(%s), CURRENT_TIMESTAMP()
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
