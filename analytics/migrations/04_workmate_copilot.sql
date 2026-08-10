-- 04_workmate_copilot.sql: Create WORKMATE_COPILOT schema runtime execution tables

CREATE TABLE IF NOT EXISTS WORKMATE_COPILOT.conversations (
    id VARCHAR(64) PRIMARY KEY,
    user_id VARCHAR(64) NOT NULL REFERENCES SECURITY.users(id),
    current_step INT NOT NULL DEFAULT 0,
    abandon_reason TEXT NULL,
    department_id VARCHAR(64) NOT NULL REFERENCES SECURITY.departments(id),
    started_at TIMESTAMP_NTZ NOT NULL DEFAULT CURRENT_TIMESTAMP(),
    ended_at TIMESTAMP_NTZ NULL
);

CREATE TABLE IF NOT EXISTS WORKMATE_COPILOT.conversation_messages (
    id VARCHAR(64) PRIMARY KEY,
    conversation_id VARCHAR(64) NOT NULL REFERENCES WORKMATE_COPILOT.conversations(id),
    sender VARCHAR(16) NOT NULL CHECK (sender IN ('employee', 'ai')),
    message_text TEXT NOT NULL,
    intent VARCHAR(128) NULL,
    retrieved_state_ids ARRAY NULL,
    citations VARIANT NULL,
    confidence_score FLOAT NOT NULL DEFAULT 0.0,
    escalated BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP_NTZ NOT NULL DEFAULT CURRENT_TIMESTAMP()
);

CREATE TABLE IF NOT EXISTS WORKMATE_COPILOT.workflow_sessions (
    id VARCHAR(64) PRIMARY KEY,
    conversation_id VARCHAR(64) NOT NULL REFERENCES WORKMATE_COPILOT.conversations(id),
    workflow_version_id VARCHAR(64) NOT NULL REFERENCES KNOWLEDGE_STUDIO.workflow_versions(id),
    current_state_id VARCHAR(64) NOT NULL REFERENCES KNOWLEDGE_STUDIO.workflow_states(id),
    previous_state_id VARCHAR(64) NULL REFERENCES KNOWLEDGE_STUDIO.workflow_states(id),
    user_id VARCHAR(64) NOT NULL REFERENCES SECURITY.users(id),
    status VARCHAR(32) NOT NULL CHECK (status IN ('active', 'paused', 'completed', 'abandoned', 'escalated')),
    session_context VARIANT NOT NULL DEFAULT PARSE_JSON('{}'),
    started_at TIMESTAMP_NTZ NOT NULL DEFAULT CURRENT_TIMESTAMP(),
    updated_at TIMESTAMP_NTZ NOT NULL DEFAULT CURRENT_TIMESTAMP(),
    completed_at TIMESTAMP_NTZ NULL
);

ALTER TABLE WORKMATE_COPILOT.workflow_sessions CLUSTER BY (user_id, status);

CREATE TABLE IF NOT EXISTS WORKMATE_COPILOT.workflow_step_executions (
    id VARCHAR(64) PRIMARY KEY,
    session_id VARCHAR(64) NOT NULL REFERENCES WORKMATE_COPILOT.workflow_sessions(id),
    step_id VARCHAR(64) NOT NULL REFERENCES KNOWLEDGE_STUDIO.workflow_steps(id),
    status VARCHAR(32) NOT NULL CHECK (status IN ('PENDING', 'PASSED', 'FAILED_VALIDATION', 'SKIPPED')),
    input_payload VARIANT NULL,
    ai_guidance_text TEXT NULL,
    execution_time_ms INT NOT NULL DEFAULT 0,
    executed_at TIMESTAMP_NTZ NOT NULL DEFAULT CURRENT_TIMESTAMP()
);

CREATE TABLE IF NOT EXISTS WORKMATE_COPILOT.workflow_evidence_submissions (
    id VARCHAR(64) PRIMARY KEY,
    step_execution_id VARCHAR(64) NOT NULL REFERENCES WORKMATE_COPILOT.workflow_step_executions(id),
    evidence_spec_id VARCHAR(64) NOT NULL REFERENCES KNOWLEDGE_STUDIO.workflow_evidence_specs(id),
    stage_file_uri VARCHAR(1024) NULL,
    text_payload TEXT NULL,
    verification_status VARCHAR(32) NOT NULL DEFAULT 'VERIFIED',
    created_at TIMESTAMP_NTZ NOT NULL DEFAULT CURRENT_TIMESTAMP()
);

CREATE TABLE IF NOT EXISTS WORKMATE_COPILOT.escalation_records (
    id VARCHAR(64) PRIMARY KEY,
    session_id VARCHAR(64) NULL REFERENCES WORKMATE_COPILOT.workflow_sessions(id),
    conversation_message_id VARCHAR(64) NULL REFERENCES WORKMATE_COPILOT.conversation_messages(id),
    escalation_policy_id VARCHAR(64) NULL REFERENCES KNOWLEDGE_STUDIO.workflow_escalation_policies(id),
    reason VARCHAR(255) NOT NULL,
    status VARCHAR(32) NOT NULL CHECK (status IN ('open', 'notified', 'resolved')),
    assigned_to_user_id VARCHAR(64) NULL REFERENCES SECURITY.users(id),
    resolution_note TEXT NULL,
    notified_at TIMESTAMP_NTZ NULL,
    created_at TIMESTAMP_NTZ NOT NULL DEFAULT CURRENT_TIMESTAMP(),
    updated_at TIMESTAMP_NTZ NOT NULL DEFAULT CURRENT_TIMESTAMP(),
    resolved_at TIMESTAMP_NTZ NULL
);
