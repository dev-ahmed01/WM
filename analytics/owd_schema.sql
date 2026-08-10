-- ============================================================================
-- WorkMate AI — Enterprise Operational Workflow Definition (OWD) Engine Schema
-- Database: WORKMATE_AI (Snowflake)
-- ============================================================================

-- 1. CREATE SCHEMAS
CREATE SCHEMA IF NOT EXISTS SECURITY;
CREATE SCHEMA IF NOT EXISTS RAW;
CREATE SCHEMA IF NOT EXISTS STAGING;
CREATE SCHEMA IF NOT EXISTS KNOWLEDGE_STUDIO;
CREATE SCHEMA IF NOT EXISTS WORKMATE_COPILOT;
CREATE SCHEMA IF NOT EXISTS INTELLIGENCE_HUB;
CREATE SCHEMA IF NOT EXISTS SHARED;
CREATE SCHEMA IF NOT EXISTS APP;

-- ============================================================================
-- 2. SECURITY SCHEMA
-- ============================================================================

CREATE TABLE IF NOT EXISTS SECURITY.departments (
    id VARCHAR(64) PRIMARY KEY,
    code VARCHAR(64) NOT NULL UNIQUE,
    name VARCHAR(255) NOT NULL,
    created_at TIMESTAMP_NTZ NOT NULL DEFAULT CURRENT_TIMESTAMP()
);

CREATE TABLE IF NOT EXISTS SECURITY.roles (
    id VARCHAR(64) PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    permission_set VARIANT NOT NULL,
    created_at TIMESTAMP_NTZ NOT NULL DEFAULT CURRENT_TIMESTAMP()
);

CREATE TABLE IF NOT EXISTS SECURITY.users (
    id VARCHAR(64) PRIMARY KEY,
    email VARCHAR(255) NOT NULL UNIQUE,
    hashed_password VARCHAR(255) NOT NULL,
    department_id VARCHAR(64) NOT NULL REFERENCES SECURITY.departments(id),
    full_name VARCHAR(255) NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'active',
    created_at TIMESTAMP_NTZ NOT NULL DEFAULT CURRENT_TIMESTAMP()
);

CREATE TABLE IF NOT EXISTS SECURITY.user_roles (
    user_id VARCHAR(64) NOT NULL REFERENCES SECURITY.users(id),
    role_id VARCHAR(64) NOT NULL REFERENCES SECURITY.roles(id),
    PRIMARY KEY (user_id, role_id)
);

-- ============================================================================
-- 3. KNOWLEDGE_STUDIO SCHEMA (OWD Relational Workflow Definitions)
-- ============================================================================

-- Workflows
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

-- Workflow Versions
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

-- Workflow States (Nodes in FSM)
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

-- Workflow Atomic Steps
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

-- Workflow Transitions (Graph Edges & Conditional Branching)
CREATE TABLE IF NOT EXISTS KNOWLEDGE_STUDIO.workflow_transitions (
    id VARCHAR(64) PRIMARY KEY,
    from_state_id VARCHAR(64) NOT NULL REFERENCES KNOWLEDGE_STUDIO.workflow_states(id),
    to_state_id VARCHAR(64) NOT NULL REFERENCES KNOWLEDGE_STUDIO.workflow_states(id),
    condition_type VARCHAR(32) NOT NULL CHECK (condition_type IN ('ALWAYS', 'EXPRESSION', 'DECISION_OPTION', 'RULE_PASS', 'RULE_FAIL', 'FALLBACK')),
    condition_expression TEXT NULL,
    priority INT NOT NULL DEFAULT 10
);

ALTER TABLE KNOWLEDGE_STUDIO.workflow_transitions CLUSTER BY (from_state_id, priority);

-- Workflow Decision Nodes & Options
CREATE TABLE IF NOT EXISTS KNOWLEDGE_STUDIO.workflow_decision_options (
    id VARCHAR(64) PRIMARY KEY,
    state_id VARCHAR(64) NOT NULL REFERENCES KNOWLEDGE_STUDIO.workflow_states(id),
    option_code VARCHAR(128) NOT NULL,
    option_label VARCHAR(255) NOT NULL,
    target_state_id VARCHAR(64) NOT NULL REFERENCES KNOWLEDGE_STUDIO.workflow_states(id)
);

-- Workflow Safety & Validation Rules
CREATE TABLE IF NOT EXISTS KNOWLEDGE_STUDIO.workflow_rules (
    id VARCHAR(64) PRIMARY KEY,
    state_id VARCHAR(64) NOT NULL REFERENCES KNOWLEDGE_STUDIO.workflow_states(id),
    rule_type VARCHAR(32) NOT NULL CHECK (rule_type IN ('SAFETY_GUARDRAIL', 'INPUT_VALIDATION', 'PREREQUISITE', 'COMPLIANCE_CHECK')),
    rule_code VARCHAR(128) NOT NULL,
    condition_logic TEXT NOT NULL,
    enforcement_level VARCHAR(32) NOT NULL CHECK (enforcement_level IN ('HARD_STOP', 'WARNING_CONFIRM', 'SUPERVISOR_OVERRIDE')),
    error_message TEXT NOT NULL
);

-- Workflow Evidence Specifications
CREATE TABLE IF NOT EXISTS KNOWLEDGE_STUDIO.workflow_evidence_specs (
    id VARCHAR(64) PRIMARY KEY,
    step_id VARCHAR(64) NOT NULL REFERENCES KNOWLEDGE_STUDIO.workflow_steps(id),
    evidence_type VARCHAR(32) NOT NULL CHECK (evidence_type IN ('DOCUMENT_PDF', 'PHOTO_JPEG', 'DIGITAL_SIGNATURE', 'CHECKSUM_HASH', 'SUPERVISOR_APPROVAL')),
    validation_regex VARCHAR(512) NULL,
    min_size_bytes INT NULL,
    is_required BOOLEAN NOT NULL DEFAULT TRUE
);

-- Workflow Escalation Policies
CREATE TABLE IF NOT EXISTS KNOWLEDGE_STUDIO.workflow_escalation_policies (
    id VARCHAR(64) PRIMARY KEY,
    state_id VARCHAR(64) NOT NULL REFERENCES KNOWLEDGE_STUDIO.workflow_states(id),
    trigger_condition VARCHAR(32) NOT NULL CHECK (trigger_condition IN ('LOW_CONFIDENCE', 'SAFETY_VIOLATION', 'USER_REQUEST', 'TIMEOUT', 'MAX_RETRIES_EXCEEDED')),
    target_role_id VARCHAR(64) NOT NULL REFERENCES SECURITY.roles(id),
    escalation_channel VARCHAR(64) NOT NULL DEFAULT 'N8N_WEBHOOK',
    notification_template TEXT NOT NULL
);

-- Workflow Search Metadata (replaces knowledge_chunks for local semantic indexing)
CREATE TABLE IF NOT EXISTS KNOWLEDGE_STUDIO.workflow_search_metadata (
    id VARCHAR(64) PRIMARY KEY,
    workflow_version_id VARCHAR(64) NOT NULL REFERENCES KNOWLEDGE_STUDIO.workflow_versions(id),
    state_id VARCHAR(64) NOT NULL REFERENCES KNOWLEDGE_STUDIO.workflow_states(id),
    department_id VARCHAR(64) NOT NULL REFERENCES SECURITY.departments(id),
    search_content TEXT NOT NULL,
    embedding_ref VARCHAR(255) NOT NULL DEFAULT 'none',
    status VARCHAR(32) NOT NULL CHECK (status IN ('published', 'archived', 'staged'))
);

ALTER TABLE KNOWLEDGE_STUDIO.workflow_search_metadata CLUSTER BY (status, department_id);

-- Enable 7-Day Time Travel Data Retention on Core Knowledge Tables
ALTER TABLE KNOWLEDGE_STUDIO.workflows SET DATA_RETENTION_TIME_IN_DAYS = 7;
ALTER TABLE KNOWLEDGE_STUDIO.workflow_versions SET DATA_RETENTION_TIME_IN_DAYS = 7;

-- 2.1 Enterprise Knowledge Document Layer Tables
CREATE TABLE IF NOT EXISTS KNOWLEDGE_STUDIO.knowledge_documents (
    id VARCHAR(64) PRIMARY KEY,
    workflow_id VARCHAR(64) NOT NULL REFERENCES KNOWLEDGE_STUDIO.workflows(id),
    workflow_version_id VARCHAR(64) NOT NULL REFERENCES KNOWLEDGE_STUDIO.workflow_versions(id),
    document_name VARCHAR(255) NOT NULL,
    original_filename VARCHAR(255) NOT NULL,
    stage_uri VARCHAR(512) NOT NULL,
    relative_path VARCHAR(512) NULL,
    directory VARCHAR(255) NULL,
    extension VARCHAR(32) NOT NULL DEFAULT 'md',
    mime_type VARCHAR(64) NOT NULL DEFAULT 'text/markdown',
    uploaded_at TIMESTAMP_NTZ NOT NULL DEFAULT CURRENT_TIMESTAMP(),
    stage_last_modified TIMESTAMP_NTZ NULL,
    file_size_bytes INT NOT NULL DEFAULT 0,
    compression VARCHAR(32) NOT NULL DEFAULT 'none',
    encoding VARCHAR(32) NOT NULL DEFAULT 'utf-8',
    md5_hash VARCHAR(64) NULL,
    sha256_hash VARCHAR(64) NOT NULL,
    compiler_version VARCHAR(32) NOT NULL DEFAULT '1.1.0',
    parser_version VARCHAR(32) NOT NULL DEFAULT '1.1.0',
    source_type VARCHAR(64) NOT NULL DEFAULT 'OWD_MARKDOWN',
    language_code VARCHAR(16) NOT NULL DEFAULT 'en-US',
    author VARCHAR(128) NULL,
    reviewer VARCHAR(128) NULL,
    approval_status VARCHAR(32) NOT NULL DEFAULT 'APPROVED',
    tags VARIANT NULL,
    labels VARIANT NULL,
    description TEXT NULL,
    created_at TIMESTAMP_NTZ NOT NULL DEFAULT CURRENT_TIMESTAMP(),
    updated_at TIMESTAMP_NTZ NOT NULL DEFAULT CURRENT_TIMESTAMP()
);

CREATE TABLE IF NOT EXISTS KNOWLEDGE_STUDIO.knowledge_document_contents (
    id VARCHAR(64) PRIMARY KEY,
    document_id VARCHAR(64) NOT NULL REFERENCES KNOWLEDGE_STUDIO.knowledge_documents(id),
    workflow_version_id VARCHAR(64) NOT NULL REFERENCES KNOWLEDGE_STUDIO.workflow_versions(id),
    raw_markdown TEXT NOT NULL,
    normalized_markdown TEXT NOT NULL,
    frontmatter_yaml TEXT NULL,
    frontmatter_json VARIANT NULL,
    body_markdown TEXT NOT NULL,
    sections_json VARIANT NULL,
    tables_json VARIANT NULL,
    code_blocks_json VARIANT NULL,
    images_json VARIANT NULL,
    links_json VARIANT NULL,
    created_at TIMESTAMP_NTZ NOT NULL DEFAULT CURRENT_TIMESTAMP()
);

CREATE TABLE IF NOT EXISTS KNOWLEDGE_STUDIO.knowledge_document_ai_metadata (
    id VARCHAR(64) PRIMARY KEY,
    document_id VARCHAR(64) NOT NULL REFERENCES KNOWLEDGE_STUDIO.knowledge_documents(id),
    workflow_version_id VARCHAR(64) NOT NULL REFERENCES KNOWLEDGE_STUDIO.workflow_versions(id),
    reading_time_minutes INT NOT NULL DEFAULT 1,
    word_count INT NOT NULL DEFAULT 0,
    sentence_count INT NOT NULL DEFAULT 0,
    paragraph_count INT NOT NULL DEFAULT 0,
    complexity_score FLOAT NOT NULL DEFAULT 0.5,
    risk_score FLOAT NOT NULL DEFAULT 0.1,
    summary TEXT NULL,
    keywords VARIANT NULL,
    entities VARIANT NULL,
    language_detected VARCHAR(16) NOT NULL DEFAULT 'en-US',
    embedding_model VARCHAR(128) NOT NULL DEFAULT 'none',
    embedding_version VARCHAR(32) NOT NULL DEFAULT 'none',
    chunk_count INT NOT NULL DEFAULT 0,
    average_chunk_size INT NOT NULL DEFAULT 0,
    last_embedding_time TIMESTAMP_NTZ NULL,
    embedding_status VARCHAR(32) NOT NULL DEFAULT 'NOT_REQUIRED',
    evaluation_score FLOAT NULL DEFAULT NULL,
    confidence_score FLOAT NULL DEFAULT NULL,
    created_at TIMESTAMP_NTZ NOT NULL DEFAULT CURRENT_TIMESTAMP()
);

CREATE TABLE IF NOT EXISTS KNOWLEDGE_STUDIO.knowledge_document_chunks (
    id VARCHAR(64) PRIMARY KEY,
    document_id VARCHAR(64) NOT NULL REFERENCES KNOWLEDGE_STUDIO.knowledge_documents(id),
    workflow_version_id VARCHAR(64) NOT NULL REFERENCES KNOWLEDGE_STUDIO.workflow_versions(id),
    state_id VARCHAR(64) NULL REFERENCES KNOWLEDGE_STUDIO.workflow_states(id),
    step_id VARCHAR(64) NULL REFERENCES KNOWLEDGE_STUDIO.workflow_steps(id),
    chunk_order INT NOT NULL DEFAULT 0,
    character_count INT NOT NULL DEFAULT 0,
    token_count INT NOT NULL DEFAULT 0,
    chunk_content TEXT NOT NULL,
    embedding_ref VARCHAR(128) NOT NULL DEFAULT 'none',
    vector_status VARCHAR(32) NOT NULL DEFAULT 'NOT_REQUIRED',
    chunk_hash VARCHAR(64) NOT NULL,
    chunk_type VARCHAR(64) NOT NULL DEFAULT 'STATE_STEP',
    section_name VARCHAR(255) NULL,
    created_at TIMESTAMP_NTZ NOT NULL DEFAULT CURRENT_TIMESTAMP()
);

CREATE TABLE IF NOT EXISTS KNOWLEDGE_STUDIO.knowledge_document_lineage (
    id VARCHAR(64) PRIMARY KEY,
    document_id VARCHAR(64) NOT NULL REFERENCES KNOWLEDGE_STUDIO.knowledge_documents(id),
    workflow_version_id VARCHAR(64) NOT NULL REFERENCES KNOWLEDGE_STUDIO.workflow_versions(id),
    stage_file_uri VARCHAR(512) NOT NULL,
    source_markdown_hash VARCHAR(64) NOT NULL,
    parser_name VARCHAR(64) NOT NULL DEFAULT 'OWDParser',
    ast_hash VARCHAR(64) NOT NULL,
    compiler_name VARCHAR(64) NOT NULL DEFAULT 'OWDCompiler',
    loader_name VARCHAR(64) NOT NULL DEFAULT 'OWDLoader',
    status VARCHAR(32) NOT NULL DEFAULT 'PUBLISHED',
    executed_by VARCHAR(128) NOT NULL DEFAULT 'SYSTEM',
    execution_notes TEXT NULL,
    created_at TIMESTAMP_NTZ NOT NULL DEFAULT CURRENT_TIMESTAMP()
);

-- ============================================================================
-- 4. WORKMATE_COPILOT SCHEMA (Runtime Engine)
-- ============================================================================

CREATE TABLE IF NOT EXISTS WORKMATE_COPILOT.conversations (
    id VARCHAR(64) PRIMARY KEY,
    user_id VARCHAR(64) NOT NULL REFERENCES SECURITY.users(id),
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
    session_id VARCHAR(64) NOT NULL REFERENCES WORKMATE_COPILOT.workflow_sessions(id),
    conversation_message_id VARCHAR(64) NULL REFERENCES WORKMATE_COPILOT.conversation_messages(id),
    escalation_policy_id VARCHAR(64) NULL REFERENCES KNOWLEDGE_STUDIO.workflow_escalation_policies(id),
    reason VARCHAR(255) NOT NULL,
    status VARCHAR(32) NOT NULL CHECK (status IN ('open', 'notified', 'resolved')),
    assigned_to_user_id VARCHAR(64) NULL REFERENCES SECURITY.users(id),
    resolution_note TEXT NULL,
    created_at TIMESTAMP_NTZ NOT NULL DEFAULT CURRENT_TIMESTAMP(),
    resolved_at TIMESTAMP_NTZ NULL
);

-- ============================================================================
-- 5. INTELLIGENCE_HUB SCHEMA (Analytics Telemetry)
-- ============================================================================

CREATE TABLE IF NOT EXISTS INTELLIGENCE_HUB.workflow_analytics_events (
    id VARCHAR(64) PRIMARY KEY,
    session_id VARCHAR(64) NOT NULL,
    workflow_version_id VARCHAR(64) NOT NULL,
    state_id VARCHAR(64) NULL,
    step_id VARCHAR(64) NULL,
    event_type VARCHAR(128) NOT NULL CHECK (event_type IN (
        'SESSION_STARTED', 'STATE_ENTERED', 'STEP_COMPLETED', 
        'DECISION_SUBMITTED', 'RULE_VIOLATED', 'EVIDENCE_SUBMITTED', 
        'ESCALATED', 'SESSION_COMPLETED', 'SESSION_ABANDONED'
    )),
    duration_ms INT NULL,
    event_payload VARIANT NULL,
    created_at TIMESTAMP_NTZ NOT NULL DEFAULT CURRENT_TIMESTAMP()
);

ALTER TABLE INTELLIGENCE_HUB.workflow_analytics_events CLUSTER BY (event_type, created_at);

-- Snowflake Dynamic Table for Real-Time Operational Telemetry Aggregation
CREATE OR REPLACE DYNAMIC TABLE INTELLIGENCE_HUB.dt_workflow_telemetry_summary
    TARGET_LAG = '1 minute'
    WAREHOUSE = COMPUTE_WH
AS
SELECT 
    workflow_version_id,
    event_type,
    COUNT(id) AS total_events,
    AVG(duration_ms) AS avg_duration_ms,
    MAX(created_at) AS last_event_at
FROM INTELLIGENCE_HUB.workflow_analytics_events
GROUP BY workflow_version_id, event_type;

-- ============================================================================
-- 6. SHARED SCHEMA (Audit & Config)
-- ============================================================================

CREATE TABLE IF NOT EXISTS SHARED.audit_logs (
    id VARCHAR(64) PRIMARY KEY,
    user_id VARCHAR(64) NOT NULL,
    action VARCHAR(255) NOT NULL,
    resource VARCHAR(255) NOT NULL,
    ip_address VARCHAR(45) NOT NULL,
    created_at TIMESTAMP_NTZ NOT NULL DEFAULT CURRENT_TIMESTAMP()
);

