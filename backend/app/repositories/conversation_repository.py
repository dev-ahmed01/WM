# Snowflake SQL Persistence Layer for Conversations & Conversation Messages

import uuid
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
    def get_or_create_session(user_id: str, session_id: Optional[str] = None) -> str:
        now = datetime.now(timezone.utc)
        if session_id:
            query = "SELECT id FROM conversations WHERE id = %s AND user_id = %s"
            try:
                with get_snowflake_connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute(query, (session_id, user_id))
                        row = cur.fetchone()
                        if row:
                            return row[0]
            except Exception as e:
                raise DatabaseException(message=f"Failed to fetch conversation session: {str(e)}")

        new_id = f"conv_{uuid.uuid4().hex[:12]}"

        insert_query = "INSERT INTO conversations (id, user_id, started_at) VALUES (%s, %s, %s)"
        try:
            with get_snowflake_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(insert_query, (new_id, user_id, now))
            return new_id
        except Exception as e:
            raise DatabaseException(message=f"Failed to create conversation session: {str(e)}")

    @staticmethod
    def load_history(conversation_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        query = """
            SELECT id, sender, message_text AS content, confidence_score, created_at
            FROM conversation_messages
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
                    return list(reversed(messages))
        except Exception as e:
            raise DatabaseException(message=f"Failed to load conversation history: {str(e)}")

    get_history = load_history

    @staticmethod
    def persist_message(
        conversation_id: str,
        sender: str,
        content: str,
        confidence_score: float = 1.0,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        msg_id = f"msg_{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc)

        query = """
            INSERT INTO conversation_messages (
                id, conversation_id, sender, message_text, confidence_score, created_at
            ) VALUES (%s, %s, %s, %s, %s, %s)
        """
        try:
            with get_snowflake_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(query, (msg_id, conversation_id, sender, content, confidence_score, now))
            return msg_id
        except Exception as e:
            raise DatabaseException(message=f"Failed to persist conversation message: {str(e)}")

    @staticmethod
    def list_user_conversations(user_id: str, limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
        """Lists past conversation sessions for a user, deriving title preview and workflow status."""
        conversations = []
        try:
            with get_snowflake_connection() as conn:
                with conn.cursor() as cur:
                    query = """
                        SELECT id, user_id, created_at, updated_at
                        FROM conversations
                        WHERE user_id = %s
                        ORDER BY updated_at DESC, created_at DESC
                        LIMIT %s OFFSET %s
                    """
                    cur.execute(query, (user_id, limit, offset))
                    rows = cur.fetchall()
                    if rows:
                        columns = [col[0].lower() for col in cur.description]
                        conversations = [dict(zip(columns, row)) for row in rows]
        except Exception:
            try:
                with get_snowflake_connection() as conn:
                    with conn.cursor() as cur:
                        query = """
                            SELECT id, user_id, started_at AS created_at, ended_at AS updated_at
                            FROM conversations
                            WHERE user_id = %s
                            ORDER BY started_at DESC
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

            raw_title = first_emp_msg.get("content") or first_emp_msg.get("message_text") if first_emp_msg else "Copilot Operational Query"
            title = raw_title[:57] + "..." if len(raw_title) > 60 else raw_title

            raw_preview = last_msg.get("content") or last_msg.get("message_text") if last_msg else ""
            preview = raw_preview[:77] + "..." if len(raw_preview) > 80 else raw_preview

            started_at = conv.get("created_at") or conv.get("started_at")
            if isinstance(started_at, datetime):
                started_at_str = started_at.isoformat()
            else:
                started_at_str = str(started_at) if started_at else datetime.now(timezone.utc).isoformat()

            results.append({
                "id": conv_id,
                "title": title,
                "status": "completed" if conv.get("updated_at") or conv.get("ended_at") else "active",
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
                    cur.execute("SELECT COUNT(*) FROM conversations WHERE user_id = %s", (user_id,))
                    row = cur.fetchone()
                    return row[0] if row else 0
        except Exception:
            return 0
