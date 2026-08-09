-- Provision objects used directly by the FastAPI runtime.
-- Run this migration with an object-owning deployment role, not the backend role.

CREATE STAGE IF NOT EXISTS KNOWLEDGE_STUDIO.RAW_OWD_STAGE
    DIRECTORY = (ENABLE = TRUE)
    COMMENT = 'Version-scoped source files uploaded by the WorkMate OWD ingestion service';

ALTER TABLE WORKMATE_COPILOT.escalation_records
    ALTER COLUMN session_id DROP NOT NULL;

ALTER TABLE WORKMATE_COPILOT.escalation_records
    ADD COLUMN IF NOT EXISTS notified_at TIMESTAMP_NTZ NULL;

ALTER TABLE WORKMATE_COPILOT.escalation_records
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP_NTZ NOT NULL DEFAULT CURRENT_TIMESTAMP();

CREATE TABLE IF NOT EXISTS INTELLIGENCE_HUB.analytics_events (
    id VARCHAR(64) PRIMARY KEY,
    event_type VARCHAR(128) NOT NULL,
    conversation_message_id VARCHAR(64) NULL,
    workflow_version_id VARCHAR(64) NULL,
    payload VARIANT NOT NULL DEFAULT PARSE_JSON('{}'),
    created_at TIMESTAMP_NTZ NOT NULL DEFAULT CURRENT_TIMESTAMP()
);

ALTER TABLE WORKMATE_COPILOT.workflow_sessions
    ADD COLUMN IF NOT EXISTS current_step INT NOT NULL DEFAULT 0;

ALTER TABLE WORKMATE_COPILOT.workflow_sessions
    ADD COLUMN IF NOT EXISTS abandon_reason TEXT NULL;

-- Required runtime grants are account-specific and deliberately use a placeholder.
-- Apply equivalent grants after replacing WORKMATE_BACKEND_ROLE with the actual role:
-- GRANT USAGE ON DATABASE WORKMATE_AI TO ROLE WORKMATE_BACKEND_ROLE;
-- GRANT USAGE ON ALL SCHEMAS IN DATABASE WORKMATE_AI TO ROLE WORKMATE_BACKEND_ROLE;
-- GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN DATABASE WORKMATE_AI TO ROLE WORKMATE_BACKEND_ROLE;
-- GRANT READ, WRITE ON STAGE WORKMATE_AI.KNOWLEDGE_STUDIO.RAW_OWD_STAGE TO ROLE WORKMATE_BACKEND_ROLE;
