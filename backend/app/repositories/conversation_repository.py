# Snowflake SQL Persistence Layer for Conversations & Conversation Messages

import uuid
import json
import logging
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from app.core.config import settings
from app.core.database import get_snowflake_connection
from app.exceptions.custom_exceptions import DatabaseException

logger = logging.getLogger("workmate.conversation_repository")


class ConversationRepository:
    """Manages CRUD operations for 'conversations' and 'conversation_messages' tables in Snowflake."""

    @staticmethod
    def get_or_create_session(
        user_id: str,
        department_id: str,
        session_id: Optional[str] = None,
    ) -> str:
        now = datetime.now(timezone.utc)
        if session_id:
            query = """
                SELECT id FROM WORKMATE_COPILOT.conversations
                WHERE id = %s AND user_id = %s AND department_id = %s
            """
            try:
                with get_snowflake_connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute(query, (session_id, user_id, department_id))
                        row = cur.fetchone()
                        if row:
                            return row[0]
            except Exception as e:
                raise DatabaseException(message=f"Failed to fetch conversation session: {str(e)}")

        new_id = f"conv_{uuid.uuid4().hex[:12]}"

        insert_query = """
            INSERT INTO WORKMATE_COPILOT.conversations
                (id, user_id, department_id, started_at)
            VALUES (%s, %s, %s, %s)
        """
        try:
            with get_snowflake_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(insert_query, (new_id, user_id, department_id, now))
            return new_id
        except Exception as e:
            raise DatabaseException(message=f"Failed to create conversation session: {str(e)}")

    @staticmethod
    def _structured_value(value: Any, fallback: Any) -> Any:
        """Normalize Snowflake ARRAY/VARIANT values for reasoning and API models."""
        if value is None:
            return fallback
        if isinstance(value, str):
            try:
                return json.loads(value)
            except (TypeError, ValueError):
                return fallback
        return value

    @staticmethod
    def load_history(conversation_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        query = """
            SELECT id, sender, message_text AS content, intent, confidence_score,
                   retrieved_state_ids, citations, created_at
            FROM WORKMATE_COPILOT.conversation_messages
            WHERE conversation_id = %s
            ORDER BY created_at DESC
            LIMIT %s
        """
        try:
            with get_snowflake_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(query, (conversation_id, limit))
                    rows = cur.fetchall()
                    columns = [col[0].lower() for col in cur.description]
                    messages = [dict(zip(columns, row)) for row in rows]
                    for message in messages:
                        message["retrieved_state_ids"] = ConversationRepository._structured_value(
                            message.get("retrieved_state_ids"), []
                        )
                        message["citations"] = ConversationRepository._structured_value(
                            message.get("citations"), []
                        )
                    return list(reversed(messages))
        except Exception as e:
            raise DatabaseException(message=f"Failed to load conversation history: {str(e)}")

    get_history = load_history

    @staticmethod
    def belongs_to_user(conversation_id: str, user_id: str) -> bool:
        try:
            with get_snowflake_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT 1 FROM WORKMATE_COPILOT.conversations WHERE id = %s AND user_id = %s",
                        (conversation_id, user_id),
                    )
                    return cur.fetchone() is not None
        except Exception as exc:
            raise DatabaseException(message=f"Failed to authorize conversation history: {exc}") from exc

    @staticmethod
    def persist_message(
        conversation_id: str,
        sender: str,
        content: str,
        confidence_score: float = 0.0,
        intent: Optional[str] = None,
        retrieved_state_ids: Optional[List[str]] = None,
        citations: Optional[List[Dict[str, Any]]] = None,
        escalated: bool = False,
    ) -> str:
        msg_id = f"msg_{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc)

        query = """
            INSERT INTO WORKMATE_COPILOT.conversation_messages (
                id, conversation_id, sender, message_text, intent,
                retrieved_state_ids, citations, confidence_score, escalated, created_at
            ) SELECT %s, %s, %s, %s, %s, TO_ARRAY(PARSE_JSON(%s)),
                     PARSE_JSON(%s), %s, %s, %s
        """
        try:
            with get_snowflake_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        query,
                        (
                            msg_id,
                            conversation_id,
                            sender,
                            content,
                            intent,
                            json.dumps(retrieved_state_ids or []),
                            json.dumps(citations or []),
                            confidence_score,
                            escalated,
                            now,
                        ),
                    )
            return msg_id
        except Exception as e:
            raise DatabaseException(message=f"Failed to persist conversation message: {str(e)}")

    @staticmethod
    def update_message_intent(message_id: str, intent: str) -> bool:
        try:
            with get_snowflake_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        UPDATE WORKMATE_COPILOT.conversation_messages
                        SET intent = %s
                        WHERE id = %s AND sender = 'employee'
                        """,
                        (intent, message_id),
                    )
                    return cur.rowcount == 1
        except Exception as exc:
            raise DatabaseException(message=f"Failed to persist message intent: {exc}") from exc

    @staticmethod
    def list_user_conversations(user_id: str, limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
        """Lists past conversation sessions for a user, deriving title preview and workflow status."""
        conversations = []
        try:
            with get_snowflake_connection() as conn:
                with conn.cursor() as cur:
                    query = """
                        SELECT c.id, c.user_id, c.started_at AS created_at,
                               c.ended_at AS updated_at,
                               COALESCE(ws.status, IFF(c.ended_at IS NULL, 'active', 'completed')) AS status
                        FROM WORKMATE_COPILOT.conversations c
                        LEFT JOIN (
                            SELECT conversation_id, status
                            FROM WORKMATE_COPILOT.workflow_sessions
                            QUALIFY ROW_NUMBER() OVER (
                                PARTITION BY conversation_id ORDER BY started_at DESC
                            ) = 1
                        ) ws ON ws.conversation_id = c.id
                        WHERE c.user_id = %s
                        ORDER BY c.started_at DESC
                        LIMIT %s OFFSET %s
                    """
                    cur.execute(query, (user_id, limit, offset))
                    rows = cur.fetchall()
                    if rows:
                        columns = [col[0].lower() for col in cur.description]
                        conversations = [dict(zip(columns, row)) for row in rows]
        except Exception as exc:
            raise DatabaseException(message=f"Failed to list user conversations: {str(exc)}") from exc

        results = []
        for conv in conversations:
            conv_id = conv["id"]
            messages = ConversationRepository.load_history(conv_id, limit=5)
            first_emp_msg = next((m for m in messages if m.get("sender") == "employee"), None)
            last_msg = messages[-1] if messages else None

            raw_title_value = (
                first_emp_msg.get("content") or first_emp_msg.get("message_text")
                if first_emp_msg
                else "Copilot Operational Query"
            )
            raw_title = str(raw_title_value or "Copilot Operational Query")
            title = raw_title[:57] + "..." if len(raw_title) > 60 else raw_title

            raw_preview_value = (
                last_msg.get("content") or last_msg.get("message_text") if last_msg else ""
            )
            raw_preview = str(raw_preview_value or "")
            preview = raw_preview[:77] + "..." if len(raw_preview) > 80 else raw_preview

            started_at = conv.get("created_at") or conv.get("started_at")
            if isinstance(started_at, datetime):
                started_at_str = started_at.isoformat()
            else:
                started_at_str = str(started_at) if started_at else datetime.now(timezone.utc).isoformat()

            results.append({
                "id": conv_id,
                "title": title,
                "status": conv.get("status") or ("completed" if conv.get("updated_at") else "active"),
                "started_at": started_at_str,
                "last_message_preview": preview,
            })
        return results

    @staticmethod
    def count_user_conversations(user_id: str) -> int:
        """Counts total conversation sessions for a user."""
        try:
            with get_snowflake_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT COUNT(*) FROM WORKMATE_COPILOT.conversations WHERE user_id = %s",
                        (user_id,),
                    )
                    row = cur.fetchone()
                    return row[0] if row else 0
        except Exception as exc:
            raise DatabaseException(message=f"Failed to count user conversations: {exc}") from exc
