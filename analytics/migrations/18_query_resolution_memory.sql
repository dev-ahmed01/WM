-- Learn department-scoped query-to-SOP mappings only after explicit confirmation.

CREATE TABLE IF NOT EXISTS WORKMATE_COPILOT.query_resolution_memory (
    id VARCHAR(64) PRIMARY KEY,
    department_id VARCHAR(64) NOT NULL REFERENCES SECURITY.departments(id),
    original_query TEXT NOT NULL,
    normalized_query VARCHAR(500) NOT NULL,
    original_language VARCHAR(8) NOT NULL DEFAULT 'en',
    translated_query TEXT NOT NULL,
    workflow_version_id VARCHAR(64) NOT NULL REFERENCES KNOWLEDGE_STUDIO.workflow_versions(id),
    workflow_code VARCHAR(128) NOT NULL,
    resolution_status VARCHAR(24) NOT NULL DEFAULT 'PENDING',
    source_conversation_id VARCHAR(64) NOT NULL REFERENCES WORKMATE_COPILOT.conversations(id),
    source_message_id VARCHAR(64) NOT NULL REFERENCES WORKMATE_COPILOT.conversation_messages(id),
    resolved_by VARCHAR(64) NOT NULL REFERENCES SECURITY.users(id),
    hit_count INT NOT NULL DEFAULT 0,
    last_used_at TIMESTAMP_TZ NULL,
    created_at TIMESTAMP_TZ NOT NULL DEFAULT CURRENT_TIMESTAMP(),
    updated_at TIMESTAMP_TZ NOT NULL DEFAULT CURRENT_TIMESTAMP(),
    CONSTRAINT chk_query_resolution_status
        CHECK (resolution_status IN ('PENDING', 'CONFIRMED', 'REJECTED'))
);

ALTER TABLE WORKMATE_COPILOT.query_resolution_memory
    CLUSTER BY (department_id, resolution_status, updated_at);
