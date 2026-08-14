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
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP_NTZ NULL;

UPDATE WORKMATE_COPILOT.escalation_records
    SET updated_at = CURRENT_TIMESTAMP()
    WHERE updated_at IS NULL;

ALTER TABLE WORKMATE_COPILOT.escalation_records
    ALTER COLUMN updated_at SET NOT NULL;

CREATE TABLE IF NOT EXISTS INTELLIGENCE_HUB.analytics_events (
    id VARCHAR(64) PRIMARY KEY,
    event_type VARCHAR(128) NOT NULL,
    conversation_message_id VARCHAR(64) NULL,
    workflow_version_id VARCHAR(64) NULL,
    payload VARIANT NOT NULL DEFAULT PARSE_JSON('{}'),
    created_at TIMESTAMP_NTZ NOT NULL DEFAULT CURRENT_TIMESTAMP()
);

-- Runtime grants are account-specific. The statements below document the
-- least-privilege role expected by production; adapt the role name when the
-- deployment uses an administrator role such as SYSADMIN.
-- GRANT USAGE ON DATABASE WORKMATE_AI TO ROLE WORKMATE_BACKEND_ROLE;
-- GRANT USAGE ON ALL SCHEMAS IN DATABASE WORKMATE_AI TO ROLE WORKMATE_BACKEND_ROLE;
-- GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN DATABASE WORKMATE_AI TO ROLE WORKMATE_BACKEND_ROLE;
-- GRANT READ, WRITE ON STAGE WORKMATE_AI.KNOWLEDGE_STUDIO.RAW_OWD_STAGE TO ROLE WORKMATE_BACKEND_ROLE;
