-- 17_multilingual_voice.sql: Persist multilingual voice interactions and analytics dimensions.

CREATE TABLE IF NOT EXISTS WORKMATE_COPILOT.voice_interactions (
    id VARCHAR(64) PRIMARY KEY,
    conversation_id VARCHAR(64) NOT NULL REFERENCES WORKMATE_COPILOT.conversations(id),
    response_message_id VARCHAR(64) NULL REFERENCES WORKMATE_COPILOT.conversation_messages(id),
    user_id VARCHAR(64) NOT NULL REFERENCES SECURITY.users(id),
    original_language VARCHAR(8) NOT NULL,
    translated_language VARCHAR(8) NOT NULL,
    original_transcript TEXT NOT NULL,
    translated_transcript TEXT NOT NULL,
    response_text TEXT NOT NULL,
    transcription_confidence FLOAT NOT NULL,
    transcription_ms INT NOT NULL,
    translation_ms INT NOT NULL,
    synthesis_ms INT NOT NULL,
    audio_id VARCHAR(96) NULL,
    success BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP_NTZ NOT NULL DEFAULT CURRENT_TIMESTAMP()
);

ALTER TABLE WORKMATE_COPILOT.voice_interactions
    CLUSTER BY (original_language, created_at);

CREATE OR REPLACE VIEW INTELLIGENCE_HUB.V_ANALYTICS_VOICE_USAGE AS
SELECT
    original_language AS language,
    COUNT(*) AS voice_interaction_count,
    COUNT_IF(success) AS successful_transcriptions,
    ROUND(100 * COUNT_IF(success) / NULLIF(COUNT(*), 0), 2) AS transcription_success_rate_pct,
    AVG(translation_ms) AS avg_translation_latency_ms,
    AVG(transcription_ms) AS avg_transcription_latency_ms,
    AVG(synthesis_ms) AS avg_synthesis_latency_ms,
    MAX(created_at) AS last_used_at
FROM WORKMATE_COPILOT.voice_interactions
GROUP BY original_language;
