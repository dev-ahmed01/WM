"""Persistence for bilingual voice interaction metadata."""

import uuid
from datetime import datetime, timezone
from typing import Any

from app.core.database import get_snowflake_connection
from app.exceptions.custom_exceptions import DatabaseException


class VoiceRepository:
    @staticmethod
    def get_synthesis_source(response_message_id: str, user_id: str) -> dict[str, Any] | None:
        query = """
            SELECT response_text, original_language, audio_id
            FROM WORKMATE_COPILOT.voice_interactions
            WHERE response_message_id = %s AND user_id = %s AND success = TRUE
            ORDER BY created_at DESC
            LIMIT 1
        """
        try:
            with get_snowflake_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(query, (response_message_id, user_id))
                    row = cur.fetchone()
            if not row:
                return None
            return {
                "response_text": str(row[0]),
                "language": str(row[1]),
                "audio_id": str(row[2]) if row[2] else None,
            }
        except Exception as exc:
            raise DatabaseException(message=f"Failed to load voice response: {exc}") from exc

    @staticmethod
    def attach_audio(
        response_message_id: str, user_id: str, audio_id: str, synthesis_ms: int
    ) -> None:
        query = """
            UPDATE WORKMATE_COPILOT.voice_interactions
            SET audio_id = %s, synthesis_ms = %s
            WHERE response_message_id = %s AND user_id = %s AND success = TRUE
        """
        try:
            with get_snowflake_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        query,
                        (audio_id, synthesis_ms, response_message_id, user_id),
                    )
        except Exception as exc:
            raise DatabaseException(message=f"Failed to attach voice audio: {exc}") from exc

    @staticmethod
    def audio_belongs_to_user(audio_id: str, user_id: str) -> bool:
        query = """
            SELECT 1 FROM WORKMATE_COPILOT.voice_interactions
            WHERE audio_id = %s AND user_id = %s AND success = TRUE
            LIMIT 1
        """
        try:
            with get_snowflake_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(query, (audio_id, user_id))
                    return cur.fetchone() is not None
        except Exception as exc:
            raise DatabaseException(
                message=f"Failed to authorize voice audio: {exc}"
            ) from exc

    @staticmethod
    def persist_interaction(
        *,
        conversation_id: str,
        response_message_id: str | None,
        user_id: str,
        original_language: str,
        translated_language: str,
        original_transcript: str,
        translated_transcript: str,
        response_text: str,
        transcription_confidence: float,
        transcription_ms: int,
        translation_ms: int,
        synthesis_ms: int,
        audio_id: str | None,
        success: bool,
    ) -> str:
        interaction_id = f"voice_{uuid.uuid4().hex[:12]}"
        query = """
            INSERT INTO WORKMATE_COPILOT.voice_interactions (
                id, conversation_id, response_message_id, user_id,
                original_language, translated_language, original_transcript,
                translated_transcript, response_text, transcription_confidence,
                transcription_ms, translation_ms, synthesis_ms, audio_id,
                success, created_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        params: tuple[Any, ...] = (
            interaction_id, conversation_id, response_message_id, user_id,
            original_language, translated_language, original_transcript,
            translated_transcript, response_text, transcription_confidence,
            transcription_ms, translation_ms, synthesis_ms, audio_id,
            success, datetime.now(timezone.utc),
        )
        try:
            with get_snowflake_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(query, params)
            return interaction_id
        except Exception as exc:
            raise DatabaseException(
                message=f"Failed to persist voice interaction: {exc}"
            ) from exc
