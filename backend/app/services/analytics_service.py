"""Analytics Service layer executing optimized read-only queries and recording telemetry in Snowflake."""

import uuid
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from app.core.database import get_snowflake_connection
from app.exceptions.custom_exceptions import DatabaseException

logger = logging.getLogger("workmate.analytics_service")


class AnalyticsService:
    """Service handling Manager Intelligence Hub data retrievals and telemetry recording."""

    @staticmethod
    def record_event(
        event_type: str,
        conversation_message_id: Optional[str] = None,
        workflow_version_id: Optional[str] = None,
        payload: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Inserts a raw telemetry event into the analytics_events table in Snowflake."""
        event_id = f"evt_{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc)
        payload_json = json.dumps(payload or {})

        query = """
            INSERT INTO INTELLIGENCE_HUB.analytics_events
                (id, event_type, conversation_message_id, workflow_version_id, payload, created_at)
            SELECT %s, %s, %s, %s, PARSE_JSON(%s), %s
        """
        try:
            with get_snowflake_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(query, (event_id, event_type, conversation_message_id, workflow_version_id, payload_json, now))
            return event_id
        except Exception as exc:
            raise DatabaseException(message=f"Failed to record analytics event: {exc}") from exc

    @staticmethod
    def get_sop_usage(department_id: Optional[str] = None) -> List[Dict[str, Any]]:
        query = "SELECT SOP_ID, SOP_TITLE, DEPARTMENT_ID, TOTAL_EXECUTIONS, UNIQUE_USERS, AVG_COMPLETION_MINUTES, LAST_USED_AT FROM INTELLIGENCE_HUB.V_ANALYTICS_SOP_USAGE"
        params = []
        if department_id:
            query += " WHERE DEPARTMENT_ID = %s"
            params.append(department_id)
        query += " ORDER BY TOTAL_EXECUTIONS DESC"

        try:
            with get_snowflake_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(query, params)
                    rows = cur.fetchall()
                    columns = [col[0].lower() for col in cur.description]
                    return [dict(zip(columns, row)) for row in rows]
        except Exception as exc:
            raise DatabaseException(message=f"Failed to load SOP usage analytics: {exc}") from exc

    @staticmethod
    def get_faqs(department_id: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        query = "SELECT QUERY_TOPIC, DEPARTMENT_ID, QUERY_COUNT, AVG_CONFIDENCE, LAST_QUERIED_AT FROM INTELLIGENCE_HUB.V_ANALYTICS_FAQS"
        params = []
        if department_id:
            query += " WHERE DEPARTMENT_ID = %s"
            params.append(department_id)
        query += " ORDER BY QUERY_COUNT DESC LIMIT %s"
        params.append(limit)

        try:
            with get_snowflake_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(query, params)
                    rows = cur.fetchall()
                    columns = [col[0].lower() for col in cur.description]
                    return [dict(zip(columns, row)) for row in rows]
        except Exception as exc:
            raise DatabaseException(message=f"Failed to load FAQ analytics: {exc}") from exc

    @staticmethod
    def get_confusing_procedures(department_id: Optional[str] = None) -> List[Dict[str, Any]]:
        query = "SELECT SOP_ID, SOP_TITLE, DEPARTMENT_ID, TOTAL_SESSIONS, CONFUSING_SESSIONS, CONFUSION_RATE_PCT, TOTAL_ESCALATIONS FROM INTELLIGENCE_HUB.V_ANALYTICS_CONFUSING_PROCEDURES"
        params = []
        if department_id:
            query += " WHERE DEPARTMENT_ID = %s"
            params.append(department_id)
        query += " ORDER BY CONFUSION_RATE_PCT DESC"

        try:
            with get_snowflake_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(query, params)
                    rows = cur.fetchall()
                    columns = [col[0].lower() for col in cur.description]
                    return [dict(zip(columns, row)) for row in rows]
        except Exception as exc:
            raise DatabaseException(message=f"Failed to load confusing-procedure analytics: {exc}") from exc

    @staticmethod
    def get_escalations(department_id: Optional[str] = None) -> List[Dict[str, Any]]:
        query = "SELECT ESCALATION_ID, SESSION_ID, USER_ID, DEPARTMENT_ID, SOP_ID, SOP_TITLE, ESCALATION_REASON, ESCALATION_STATUS, CREATED_AT FROM INTELLIGENCE_HUB.V_ANALYTICS_ESCALATIONS"
        params = []
        if department_id:
            query += " WHERE DEPARTMENT_ID = %s"
            params.append(department_id)
        query += " ORDER BY CREATED_AT DESC"

        try:
            with get_snowflake_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(query, params)
                    rows = cur.fetchall()
                    columns = [col[0].lower() for col in cur.description]
                    return [dict(zip(columns, row)) for row in rows]
        except Exception as exc:
            raise DatabaseException(message=f"Failed to load escalation analytics: {exc}") from exc

    @staticmethod
    def get_department_adoption() -> List[Dict[str, Any]]:
        query = "SELECT DEPARTMENT_ID, TOTAL_ENROLLED_USERS, ACTIVE_COPILOT_USERS, TOTAL_INTERACTIONS, ADOPTION_RATE_PCT FROM INTELLIGENCE_HUB.V_ANALYTICS_DEPARTMENT_ADOPTION ORDER BY ADOPTION_RATE_PCT DESC"
        try:
            with get_snowflake_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(query)
                    rows = cur.fetchall()
                    columns = [col[0].lower() for col in cur.description]
                    return [dict(zip(columns, row)) for row in rows]
        except Exception as exc:
            raise DatabaseException(message=f"Failed to load department adoption analytics: {exc}") from exc

    @staticmethod
    def get_confidence_trends(department_id: Optional[str] = None) -> List[Dict[str, Any]]:
        query = "SELECT METRIC_DATE, DEPARTMENT_ID, TOTAL_RESPONSES, AVG_CONFIDENCE_SCORE, MIN_CONFIDENCE_SCORE, MAX_CONFIDENCE_SCORE FROM INTELLIGENCE_HUB.V_ANALYTICS_CONFIDENCE_TRENDS"
        params = []
        if department_id:
            query += " WHERE DEPARTMENT_ID = %s"
            params.append(department_id)
        query += " ORDER BY METRIC_DATE ASC"

        try:
            with get_snowflake_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(query, params)
                    rows = cur.fetchall()
                    columns = [col[0].lower() for col in cur.description]
                    return [dict(zip(columns, row)) for row in rows]
        except Exception as exc:
            raise DatabaseException(message=f"Failed to load confidence analytics: {exc}") from exc
