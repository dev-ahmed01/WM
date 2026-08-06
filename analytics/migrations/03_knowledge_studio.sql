-- 03_knowledge_studio.sql: Create KNOWLEDGE_STUDIO schema normalized OWD tables

CREATE TABLE IF NOT EXISTS KNOWLEDGE_STUDIO.workflows (
    id VARCHAR(64) PRIMARY KEY,
    workflow_code VARCHAR(128) NOT NULL UNIQUE,
    title VARCHAR(512) NOT NULL,
    description TEXT NULL,
    department_id VARCHAR(64) NOT NULL REFERENCES SECURITY.departments(id),
    category VARCHAR(128) NOT NULL,
    created_by VARCHAR(64) NOT NULL REFERENCES SECURITY.users(id),
    created_at TIMESTAMP_NTZ NOT NULL DEFAULT CURRENT_TIMESTAMP(),
    updated_at TIMESTAMP_NTZ NOT NULL DEFAULT CURRENT_TIMESTAMP()
);

ALTER TABLE KNOWLEDGE_STUDIO.workflows CLUSTER BY (department_id, category);

CREATE TABLE IF NOT EXISTS KNOWLEDGE_STUDIO.workflow_versions (
    id VARCHAR(64) PRIMARY KEY,
    workflow_id VARCHAR(64) NOT NULL REFERENCES KNOWLEDGE_STUDIO.workflows(id),
    version_number INT NOT NULL,
    semantic_version VARCHAR(32) NOT NULL DEFAULT '1.0.0',
    stage_file_uri VARCHAR(1024) NOT NULL,
    ast_hash VARCHAR(64) NOT NULL,
    status VARCHAR(32) NOT NULL CHECK (status IN ('staged', 'compiled', 'validated', 'published', 'deprecated', 'archived', 'failed')),
    created_at TIMESTAMP_NTZ NOT NULL DEFAULT CURRENT_TIMESTAMP(),
    published_at TIMESTAMP_NTZ NULL
);

ALTER TABLE KNOWLEDGE_STUDIO.workflow_versions CLUSTER BY (status, workflow_id);

CREATE TABLE IF NOT EXISTS KNOWLEDGE_STUDIO.workflow_states (
    id VARCHAR(64) PRIMARY KEY,
    workflow_version_id VARCHAR(64) NOT NULL REFERENCES KNOWLEDGE_STUDIO.workflow_versions(id),
    state_key VARCHAR(128) NOT NULL,
    state_type VARCHAR(32) NOT NULL CHECK (state_type IN ('START', 'ATOMIC_STEP', 'DECISION', 'PARALLEL_GATE', 'ESCALATION', 'END')),
    title VARCHAR(255) NOT NULL,
    description TEXT NULL,
    is_initial BOOLEAN NOT NULL DEFAULT FALSE,
    is_terminal BOOLEAN NOT NULL DEFAULT FALSE,
    ordinal_index INT NOT NULL
);

ALTER TABLE KNOWLEDGE_STUDIO.workflow_states CLUSTER BY (workflow_version_id, ordinal_index);

CREATE TABLE IF NOT EXISTS KNOWLEDGE_STUDIO.workflow_steps (
    id VARCHAR(64) PRIMARY KEY,
    state_id VARCHAR(64) NOT NULL REFERENCES KNOWLEDGE_STUDIO.workflow_states(id),
    step_code VARCHAR(128) NOT NULL,
    instruction TEXT NOT NULL,
    ai_guidance_prompt TEXT NULL,
    expected_output_type VARCHAR(64) NOT NULL CHECK (expected_output_type IN ('CONFIRMATION', 'TEXT_INPUT', 'SINGLE_CHOICE', 'MULTI_CHOICE', 'DOCUMENT_UPLOAD', 'NUMERIC_INPUT')),
    is_mandatory BOOLEAN NOT NULL DEFAULT TRUE,
    ordinal_index INT NOT NULL
);

ALTER TABLE KNOWLEDGE_STUDIO.workflow_steps CLUSTER BY (state_id, ordinal_index);

CREATE TABLE IF NOT EXISTS KNOWLEDGE_STUDIO.workflow_transitions (
    id VARCHAR(64) PRIMARY KEY,
    from_state_id VARCHAR(64) NOT NULL REFERENCES KNOWLEDGE_STUDIO.workflow_states(id),
    to_state_id VARCHAR(64) NOT NULL REFERENCES KNOWLEDGE_STUDIO.workflow_states(id),
    condition_type VARCHAR(32) NOT NULL CHECK (condition_type IN ('ALWAYS', 'EXPRESSION', 'DECISION_OPTION', 'RULE_PASS', 'RULE_FAIL', 'FALLBACK')),
    condition_expression TEXT NULL,
    priority INT NOT NULL DEFAULT 10
);

ALTER TABLE KNOWLEDGE_STUDIO.workflow_transitions CLUSTER BY (from_state_id, priority);

CREATE TABLE IF NOT EXISTS KNOWLEDGE_STUDIO.workflow_decision_options (
    id VARCHAR(64) PRIMARY KEY,
    state_id VARCHAR(64) NOT NULL REFERENCES KNOWLEDGE_STUDIO.workflow_states(id),
    option_code VARCHAR(128) NOT NULL,
    option_label VARCHAR(255) NOT NULL,
    target_state_id VARCHAR(64) NOT NULL REFERENCES KNOWLEDGE_STUDIO.workflow_states(id)
);

CREATE TABLE IF NOT EXISTS KNOWLEDGE_STUDIO.workflow_rules (
    id VARCHAR(64) PRIMARY KEY,
    state_id VARCHAR(64) NOT NULL REFERENCES KNOWLEDGE_STUDIO.workflow_states(id),
    rule_type VARCHAR(32) NOT NULL CHECK (rule_type IN ('SAFETY_GUARDRAIL', 'INPUT_VALIDATION', 'PREREQUISITE', 'COMPLIANCE_CHECK')),
    rule_code VARCHAR(128) NOT NULL,
    condition_logic TEXT NOT NULL,
    enforcement_level VARCHAR(32) NOT NULL CHECK (enforcement_level IN ('HARD_STOP', 'WARNING_CONFIRM', 'SUPERVISOR_OVERRIDE')),
    error_message TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS KNOWLEDGE_STUDIO.workflow_evidence_specs (
    id VARCHAR(64) PRIMARY KEY,
    step_id VARCHAR(64) NOT NULL REFERENCES KNOWLEDGE_STUDIO.workflow_steps(id),
    evidence_type VARCHAR(32) NOT NULL CHECK (evidence_type IN ('DOCUMENT_PDF', 'PHOTO_JPEG', 'DIGITAL_SIGNATURE', 'CHECKSUM_HASH', 'SUPERVISOR_APPROVAL')),
    validation_regex VARCHAR(512) NULL,
    min_size_bytes INT NULL,
    is_required BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS KNOWLEDGE_STUDIO.workflow_escalation_policies (
    id VARCHAR(64) PRIMARY KEY,
    state_id VARCHAR(64) NOT NULL REFERENCES KNOWLEDGE_STUDIO.workflow_states(id),
    trigger_condition VARCHAR(32) NOT NULL CHECK (trigger_condition IN ('LOW_CONFIDENCE', 'SAFETY_VIOLATION', 'USER_REQUEST', 'TIMEOUT', 'MAX_RETRIES_EXCEEDED')),
    target_role_id VARCHAR(64) NOT NULL REFERENCES SECURITY.roles(id),
    escalation_channel VARCHAR(64) NOT NULL DEFAULT 'N8N_WEBHOOK',
    notification_template TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS KNOWLEDGE_STUDIO.workflow_search_metadata (
    id VARCHAR(64) PRIMARY KEY,
    workflow_version_id VARCHAR(64) NOT NULL REFERENCES KNOWLEDGE_STUDIO.workflow_versions(id),
    state_id VARCHAR(64) NOT NULL REFERENCES KNOWLEDGE_STUDIO.workflow_states(id),
    department_id VARCHAR(64) NOT NULL REFERENCES SECURITY.departments(id),
    search_content TEXT NOT NULL,
    embedding_ref VARCHAR(255) NOT NULL DEFAULT 'cortex_embed_e5_base_v2',
    status VARCHAR(32) NOT NULL CHECK (status IN ('published', 'archived', 'staged'))
);

ALTER TABLE KNOWLEDGE_STUDIO.workflow_search_metadata CLUSTER BY (status, department_id);
