-- PostgreSQL-only WorkMate schema (new installations; no Snowflake connection).
-- Source definitions ported from the old table DDL and audited as a separate baseline.
-- Run via scripts/migrate_postgres.py; idempotent CREATE/ADD clauses.
CREATE SCHEMA IF NOT EXISTS security;
CREATE SCHEMA IF NOT EXISTS knowledge_studio;
CREATE SCHEMA IF NOT EXISTS workmate_copilot;
CREATE SCHEMA IF NOT EXISTS intelligence_hub;
CREATE SCHEMA IF NOT EXISTS shared;

-- Converted table structures from historical 02_security.sql, without its Snowflake operations.
CREATE TABLE IF NOT EXISTS SECURITY.departments (
    id VARCHAR(64) PRIMARY KEY,
    code VARCHAR(64) NOT NULL UNIQUE,
    name VARCHAR(255) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS SECURITY.roles (
    id VARCHAR(64) PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    permission_set JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS SECURITY.users (
    id VARCHAR(64) PRIMARY KEY,
    email VARCHAR(255) NOT NULL UNIQUE,
    hashed_password VARCHAR(255) NOT NULL,
    department_id VARCHAR(64) NOT NULL REFERENCES SECURITY.departments(id),
    full_name VARCHAR(255) NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'active',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS SECURITY.user_roles (
    user_id VARCHAR(64) NOT NULL REFERENCES SECURITY.users(id),
    role_id VARCHAR(64) NOT NULL REFERENCES SECURITY.roles(id),
    PRIMARY KEY (user_id, role_id)
);

-- Converted table structures from historical 03_knowledge_studio.sql, without its Snowflake operations.
CREATE TABLE IF NOT EXISTS KNOWLEDGE_STUDIO.workflows (
    id VARCHAR(64) PRIMARY KEY,
    workflow_code VARCHAR(128) NOT NULL UNIQUE,
    title VARCHAR(512) NOT NULL,
    description TEXT NULL,
    department_id VARCHAR(64) NOT NULL REFERENCES SECURITY.departments(id),
    category VARCHAR(128) NOT NULL,
    created_by VARCHAR(64) NOT NULL REFERENCES SECURITY.users(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS KNOWLEDGE_STUDIO.workflow_versions (
    id VARCHAR(64) PRIMARY KEY,
    workflow_id VARCHAR(64) NOT NULL REFERENCES KNOWLEDGE_STUDIO.workflows(id),
    version_number INT NOT NULL,
    semantic_version VARCHAR(32) NOT NULL DEFAULT '1.0.0',
    stage_file_uri VARCHAR(1024) NOT NULL,
    ast_hash VARCHAR(64) NOT NULL,
    status VARCHAR(32) NOT NULL CHECK (status IN ('staged', 'compiled', 'validated', 'published', 'deprecated', 'archived', 'failed')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    published_at TIMESTAMPTZ NULL
);

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

CREATE TABLE IF NOT EXISTS KNOWLEDGE_STUDIO.workflow_transitions (
    id VARCHAR(64) PRIMARY KEY,
    from_state_id VARCHAR(64) NOT NULL REFERENCES KNOWLEDGE_STUDIO.workflow_states(id),
    to_state_id VARCHAR(64) NOT NULL REFERENCES KNOWLEDGE_STUDIO.workflow_states(id),
    condition_type VARCHAR(32) NOT NULL CHECK (condition_type IN ('ALWAYS', 'EXPRESSION', 'DECISION_OPTION', 'RULE_PASS', 'RULE_FAIL', 'FALLBACK')),
    condition_expression TEXT NULL,
    priority INT NOT NULL DEFAULT 10
);

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
    embedding_ref VARCHAR(255) NOT NULL DEFAULT 'none',
    status VARCHAR(32) NOT NULL CHECK (status IN ('published', 'archived', 'staged'))
);

-- Converted table structures from historical 04_workmate_copilot.sql, without its Snowflake operations.
CREATE TABLE IF NOT EXISTS WORKMATE_COPILOT.conversations (
    id VARCHAR(64) PRIMARY KEY,
    user_id VARCHAR(64) NOT NULL REFERENCES SECURITY.users(id),
    department_id VARCHAR(64) NOT NULL REFERENCES SECURITY.departments(id),
    started_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    ended_at TIMESTAMPTZ NULL
);

CREATE TABLE IF NOT EXISTS WORKMATE_COPILOT.conversation_messages (
    id VARCHAR(64) PRIMARY KEY,
    conversation_id VARCHAR(64) NOT NULL REFERENCES WORKMATE_COPILOT.conversations(id),
    sender VARCHAR(16) NOT NULL CHECK (sender IN ('employee', 'ai')),
    message_text TEXT NOT NULL,
    intent VARCHAR(128) NULL,
    retrieved_state_ids JSONB NULL,
    citations JSONB NULL,
    confidence_score FLOAT NOT NULL DEFAULT 0.0,
    escalated BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS WORKMATE_COPILOT.workflow_sessions (
    id VARCHAR(64) PRIMARY KEY,
    conversation_id VARCHAR(64) NOT NULL REFERENCES WORKMATE_COPILOT.conversations(id),
    workflow_version_id VARCHAR(64) NOT NULL REFERENCES KNOWLEDGE_STUDIO.workflow_versions(id),
    current_state_id VARCHAR(64) NOT NULL REFERENCES KNOWLEDGE_STUDIO.workflow_states(id),
    previous_state_id VARCHAR(64) NULL REFERENCES KNOWLEDGE_STUDIO.workflow_states(id),
    user_id VARCHAR(64) NOT NULL REFERENCES SECURITY.users(id),
    status VARCHAR(32) NOT NULL CHECK (status IN ('active', 'paused', 'completed', 'abandoned', 'escalated')),
    session_context JSONB NOT NULL DEFAULT '{}'::jsonb,
    started_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMPTZ NULL
);

CREATE TABLE IF NOT EXISTS WORKMATE_COPILOT.workflow_step_executions (
    id VARCHAR(64) PRIMARY KEY,
    session_id VARCHAR(64) NOT NULL REFERENCES WORKMATE_COPILOT.workflow_sessions(id),
    step_id VARCHAR(64) NOT NULL REFERENCES KNOWLEDGE_STUDIO.workflow_steps(id),
    status VARCHAR(32) NOT NULL CHECK (status IN ('PENDING', 'PASSED', 'FAILED_VALIDATION', 'SKIPPED')),
    input_payload JSONB NULL,
    ai_guidance_text TEXT NULL,
    execution_time_ms INT NOT NULL DEFAULT 0,
    executed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS WORKMATE_COPILOT.workflow_evidence_submissions (
    id VARCHAR(64) PRIMARY KEY,
    step_execution_id VARCHAR(64) NOT NULL REFERENCES WORKMATE_COPILOT.workflow_step_executions(id),
    evidence_spec_id VARCHAR(64) NOT NULL REFERENCES KNOWLEDGE_STUDIO.workflow_evidence_specs(id),
    stage_file_uri VARCHAR(1024) NULL,
    text_payload TEXT NULL,
    verification_status VARCHAR(32) NOT NULL DEFAULT 'VERIFIED',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
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
    notified_at TIMESTAMPTZ NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    resolved_at TIMESTAMPTZ NULL
);

-- Converted table structures from historical 05_intelligence_hub.sql, without its Snowflake operations.
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
    event_payload JSONB NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Converted table structures from historical 06_shared.sql, without its Snowflake operations.
CREATE TABLE IF NOT EXISTS SHARED.audit_logs (
    id VARCHAR(64) PRIMARY KEY,
    user_id VARCHAR(64) NOT NULL,
    role VARCHAR(64) NOT NULL,
    action VARCHAR(255) NOT NULL,
    resource VARCHAR(255) NOT NULL,
    ip_address VARCHAR(45) NOT NULL,
    status_code INT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Converted table structures from historical 09_owd_v1_1_tables.sql, without its Snowflake operations.
ALTER TABLE KNOWLEDGE_STUDIO.workflows ADD COLUMN IF NOT EXISTS owner VARCHAR(128) NULL;

ALTER TABLE KNOWLEDGE_STUDIO.workflows ADD COLUMN IF NOT EXISTS priority VARCHAR(32) NULL;

ALTER TABLE KNOWLEDGE_STUDIO.workflows ADD COLUMN IF NOT EXISTS difficulty VARCHAR(32) NULL;

ALTER TABLE KNOWLEDGE_STUDIO.workflows ADD COLUMN IF NOT EXISTS estimated_duration VARCHAR(64) NULL;

ALTER TABLE KNOWLEDGE_STUDIO.workflows ADD COLUMN IF NOT EXISTS review_cycle VARCHAR(64) NULL;

ALTER TABLE KNOWLEDGE_STUDIO.workflows ADD COLUMN IF NOT EXISTS effective_date VARCHAR(32) NULL;

ALTER TABLE KNOWLEDGE_STUDIO.workflows ADD COLUMN IF NOT EXISTS workflow_objective TEXT NULL;

ALTER TABLE KNOWLEDGE_STUDIO.workflows ADD COLUMN IF NOT EXISTS business_goal TEXT NULL;

ALTER TABLE KNOWLEDGE_STUDIO.workflows ADD COLUMN IF NOT EXISTS entry_conditions TEXT NULL;

ALTER TABLE KNOWLEDGE_STUDIO.workflows ADD COLUMN IF NOT EXISTS exit_conditions TEXT NULL;

ALTER TABLE KNOWLEDGE_STUDIO.workflow_states ADD COLUMN IF NOT EXISTS purpose TEXT NULL;

ALTER TABLE KNOWLEDGE_STUDIO.workflow_states ADD COLUMN IF NOT EXISTS entry_condition TEXT NULL;

ALTER TABLE KNOWLEDGE_STUDIO.workflow_states ADD COLUMN IF NOT EXISTS exit_condition TEXT NULL;

ALTER TABLE KNOWLEDGE_STUDIO.workflow_states ADD COLUMN IF NOT EXISTS responsible_role VARCHAR(128) NULL;

ALTER TABLE KNOWLEDGE_STUDIO.workflow_states ADD COLUMN IF NOT EXISTS expected_duration VARCHAR(64) NULL;

ALTER TABLE KNOWLEDGE_STUDIO.workflow_states ADD COLUMN IF NOT EXISTS business_objective TEXT NULL;

ALTER TABLE KNOWLEDGE_STUDIO.workflow_steps ADD COLUMN IF NOT EXISTS sequence_number INT NULL;

ALTER TABLE KNOWLEDGE_STUDIO.workflow_steps ADD COLUMN IF NOT EXISTS safety_note TEXT NULL;

ALTER TABLE KNOWLEDGE_STUDIO.workflow_steps ADD COLUMN IF NOT EXISTS estimated_time VARCHAR(64) NULL;

ALTER TABLE KNOWLEDGE_STUDIO.workflow_steps ADD COLUMN IF NOT EXISTS retry_policy VARCHAR(255) NULL;

ALTER TABLE KNOWLEDGE_STUDIO.workflow_steps ADD COLUMN IF NOT EXISTS completion_criteria TEXT NULL;

ALTER TABLE KNOWLEDGE_STUDIO.workflow_steps ADD COLUMN IF NOT EXISTS common_failure TEXT NULL;

ALTER TABLE KNOWLEDGE_STUDIO.workflow_steps ADD COLUMN IF NOT EXISTS recovery_action TEXT NULL;

CREATE TABLE IF NOT EXISTS KNOWLEDGE_STUDIO.workflow_decisions (
    id VARCHAR(64) PRIMARY KEY,
    state_id VARCHAR(64) NOT NULL REFERENCES KNOWLEDGE_STUDIO.workflow_states(id),
    decision_code VARCHAR(128) NOT NULL,
    question TEXT NOT NULL,
    alternative_path TEXT NULL,
    business_rule TEXT NULL,
    escalation_workflow VARCHAR(128) NULL
);

CREATE TABLE IF NOT EXISTS KNOWLEDGE_STUDIO.workflow_ai_conversation (
    id VARCHAR(64) PRIMARY KEY,
    step_id VARCHAR(64) NOT NULL REFERENCES KNOWLEDGE_STUDIO.workflow_steps(id),
    question_ai_should_ask TEXT NOT NULL,
    expected_user_responses TEXT NULL,
    clarification_questions TEXT NULL,
    fallback_prompt TEXT NULL,
    coaching_prompt TEXT NULL,
    escalation_trigger TEXT NULL,
    confidence_requirements VARCHAR(64) NULL,
    citation_source TEXT NULL
);

CREATE TABLE IF NOT EXISTS KNOWLEDGE_STUDIO.workflow_analytics (
    id VARCHAR(64) PRIMARY KEY,
    workflow_version_id VARCHAR(64) NOT NULL REFERENCES KNOWLEDGE_STUDIO.workflow_versions(id),
    event_name VARCHAR(128) NOT NULL,
    event_trigger VARCHAR(128) NOT NULL,
    kpis TEXT NULL
);

CREATE TABLE IF NOT EXISTS KNOWLEDGE_STUDIO.workflow_relationships (
    id VARCHAR(64) PRIMARY KEY,
    workflow_version_id VARCHAR(64) NOT NULL REFERENCES KNOWLEDGE_STUDIO.workflow_versions(id),
    relationship_type VARCHAR(64) NOT NULL CHECK (relationship_type IN ('PARENT_SOP', 'CHILD_SOP', 'RELATED_SOP', 'PREVIOUS_SOP', 'NEXT_SOP', 'ESCALATION_SOP', 'EXCEPTION_SOP', 'REFERENCED_EQUIPMENT', 'REFERENCED_DOCUMENT', 'REFERENCED_POLICY')),
    target_reference VARCHAR(512) NOT NULL,
    description TEXT NULL
);

CREATE TABLE IF NOT EXISTS KNOWLEDGE_STUDIO.workflow_references (
    id VARCHAR(64) PRIMARY KEY,
    workflow_version_id VARCHAR(64) NOT NULL REFERENCES KNOWLEDGE_STUDIO.workflow_versions(id),
    reference_type VARCHAR(64) NOT NULL CHECK (reference_type IN ('PRIMARY_SOURCE', 'SUPPORTING_SOURCE', 'OFFICIAL_URL', 'COMPLIANCE_STANDARD', 'DOC_SECTION')),
    title VARCHAR(512) NOT NULL,
    citation_uri TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS KNOWLEDGE_STUDIO.workflow_role_permissions (
    id VARCHAR(64) PRIMARY KEY,
    workflow_version_id VARCHAR(64) NOT NULL REFERENCES KNOWLEDGE_STUDIO.workflow_versions(id),
    role_name VARCHAR(128) NOT NULL,
    required_permissions TEXT NULL,
    experience_level VARCHAR(64) NULL,
    required_certifications TEXT NULL,
    language_code VARCHAR(32) NOT NULL DEFAULT 'en-US',
    department_id VARCHAR(64) NOT NULL REFERENCES SECURITY.departments(id)
);

-- Converted table structures from historical 10_enterprise_document_layer.sql, without its Snowflake operations.
CREATE TABLE IF NOT EXISTS KNOWLEDGE_STUDIO.KNOWLEDGE_DOCUMENTS (
    id VARCHAR(64) PRIMARY KEY,
    workflow_id VARCHAR(64) NOT NULL REFERENCES KNOWLEDGE_STUDIO.WORKFLOWS(id),
    workflow_version_id VARCHAR(64) NOT NULL REFERENCES KNOWLEDGE_STUDIO.WORKFLOW_VERSIONS(id),
    document_name VARCHAR(255) NOT NULL,
    original_filename VARCHAR(255) NOT NULL,
    stage_uri VARCHAR(512) NOT NULL,
    relative_path VARCHAR(512) NULL,
    directory VARCHAR(255) NULL,
    extension VARCHAR(32) NOT NULL DEFAULT 'md',
    mime_type VARCHAR(64) NOT NULL DEFAULT 'text/markdown',
    uploaded_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    stage_last_modified TIMESTAMPTZ NULL,
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
    tags JSONB NULL,
    labels JSONB NULL,
    description TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS KNOWLEDGE_STUDIO.KNOWLEDGE_DOCUMENT_CONTENTS (
    id VARCHAR(64) PRIMARY KEY,
    document_id VARCHAR(64) NOT NULL REFERENCES KNOWLEDGE_STUDIO.KNOWLEDGE_DOCUMENTS(id),
    workflow_version_id VARCHAR(64) NOT NULL REFERENCES KNOWLEDGE_STUDIO.WORKFLOW_VERSIONS(id),
    raw_markdown TEXT NOT NULL,
    normalized_markdown TEXT NOT NULL,
    frontmatter_yaml TEXT NULL,
    frontmatter_json JSONB NULL,
    body_markdown TEXT NOT NULL,
    sections_json JSONB NULL,
    tables_json JSONB NULL,
    code_blocks_json JSONB NULL,
    images_json JSONB NULL,
    links_json JSONB NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS KNOWLEDGE_STUDIO.KNOWLEDGE_DOCUMENT_AI_METADATA (
    id VARCHAR(64) PRIMARY KEY,
    document_id VARCHAR(64) NOT NULL REFERENCES KNOWLEDGE_STUDIO.KNOWLEDGE_DOCUMENTS(id),
    workflow_version_id VARCHAR(64) NOT NULL REFERENCES KNOWLEDGE_STUDIO.WORKFLOW_VERSIONS(id),
    reading_time_minutes INT NOT NULL DEFAULT 1,
    word_count INT NOT NULL DEFAULT 0,
    sentence_count INT NOT NULL DEFAULT 0,
    paragraph_count INT NOT NULL DEFAULT 0,
    complexity_score FLOAT NOT NULL DEFAULT 0.5,
    risk_score FLOAT NOT NULL DEFAULT 0.1,
    summary TEXT NULL,
    keywords JSONB NULL,
    entities JSONB NULL,
    language_detected VARCHAR(16) NOT NULL DEFAULT 'en-US',
    embedding_model VARCHAR(128) NOT NULL DEFAULT 'none',
    embedding_version VARCHAR(32) NOT NULL DEFAULT 'none',
    chunk_count INT NOT NULL DEFAULT 0,
    average_chunk_size INT NOT NULL DEFAULT 0,
    last_embedding_time TIMESTAMPTZ NULL,
    embedding_status VARCHAR(32) NOT NULL DEFAULT 'NOT_REQUIRED',
    evaluation_score FLOAT NULL DEFAULT NULL,
    confidence_score FLOAT NULL DEFAULT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS KNOWLEDGE_STUDIO.KNOWLEDGE_DOCUMENT_CHUNKS (
    id VARCHAR(64) PRIMARY KEY,
    document_id VARCHAR(64) NOT NULL REFERENCES KNOWLEDGE_STUDIO.KNOWLEDGE_DOCUMENTS(id),
    workflow_version_id VARCHAR(64) NOT NULL REFERENCES KNOWLEDGE_STUDIO.WORKFLOW_VERSIONS(id),
    state_id VARCHAR(64) NULL REFERENCES KNOWLEDGE_STUDIO.WORKFLOW_STATES(id),
    step_id VARCHAR(64) NULL REFERENCES KNOWLEDGE_STUDIO.WORKFLOW_STEPS(id),
    chunk_order INT NOT NULL DEFAULT 0,
    character_count INT NOT NULL DEFAULT 0,
    token_count INT NOT NULL DEFAULT 0,
    chunk_content TEXT NOT NULL,
    embedding_ref VARCHAR(128) NOT NULL DEFAULT 'none',
    vector_status VARCHAR(32) NOT NULL DEFAULT 'NOT_REQUIRED',
    chunk_hash VARCHAR(64) NOT NULL,
    chunk_type VARCHAR(64) NOT NULL DEFAULT 'STATE_STEP',
    section_name VARCHAR(255) NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS KNOWLEDGE_STUDIO.KNOWLEDGE_DOCUMENT_LINEAGE (
    id VARCHAR(64) PRIMARY KEY,
    document_id VARCHAR(64) NOT NULL REFERENCES KNOWLEDGE_STUDIO.KNOWLEDGE_DOCUMENTS(id),
    workflow_version_id VARCHAR(64) NOT NULL REFERENCES KNOWLEDGE_STUDIO.WORKFLOW_VERSIONS(id),
    stage_file_uri VARCHAR(512) NOT NULL,
    source_markdown_hash VARCHAR(64) NOT NULL,
    parser_name VARCHAR(64) NOT NULL DEFAULT 'OWDParser',
    ast_hash VARCHAR(64) NOT NULL,
    compiler_name VARCHAR(64) NOT NULL DEFAULT 'OWDCompiler',
    loader_name VARCHAR(64) NOT NULL DEFAULT 'OWDLoader',
    status VARCHAR(32) NOT NULL DEFAULT 'PUBLISHED',
    executed_by VARCHAR(128) NOT NULL DEFAULT 'SYSTEM',
    execution_notes TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Converted table structures from historical 17_multilingual_voice.sql, without its Snowflake operations.
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
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Converted table structures from historical 18_query_resolution_memory.sql, without its Snowflake operations.
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
    last_used_at TIMESTAMPTZ NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_query_resolution_status
        CHECK (resolution_status IN ('PENDING', 'CONFIRMED', 'REJECTED'))
);

-- Converted table structures from historical 19_reference_knowledge.sql, without its Snowflake operations.
CREATE TABLE IF NOT EXISTS KNOWLEDGE_STUDIO.reference_documents (
    id VARCHAR(64) PRIMARY KEY,
    department_id VARCHAR(64) NOT NULL REFERENCES SECURITY.departments(id),
    title VARCHAR(512) NOT NULL,
    original_filename VARCHAR(255) NOT NULL,
    file_extension VARCHAR(16) NOT NULL,
    mime_type VARCHAR(128) NOT NULL,
    stage_uri VARCHAR(1024) NOT NULL,
    sha256_hash VARCHAR(64) NOT NULL,
    file_size_bytes BIGINT NOT NULL,
    extracted_characters BIGINT NOT NULL,
    extraction_warnings VARCHAR(8192),
    status VARCHAR(32) NOT NULL DEFAULT 'DRAFT'
        CHECK (status IN ('DRAFT', 'APPROVED', 'ARCHIVED')),
    created_by VARCHAR(128) NOT NULL,
    reviewed_by VARCHAR(128),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    reviewed_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS KNOWLEDGE_STUDIO.reference_chunks (
    id VARCHAR(64) PRIMARY KEY,
    document_id VARCHAR(64) NOT NULL REFERENCES KNOWLEDGE_STUDIO.reference_documents(id),
    department_id VARCHAR(64) NOT NULL REFERENCES SECURITY.departments(id),
    ordinal_index BIGINT NOT NULL,
    start_offset BIGINT NOT NULL,
    end_offset BIGINT NOT NULL,
    content TEXT NOT NULL,
    sha256_hash VARCHAR(64) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS shared.source_objects (
  id VARCHAR(64) PRIMARY KEY,
  department_id VARCHAR(64) NOT NULL REFERENCES security.departments(id),
  filename VARCHAR(255) NOT NULL,
  sha256_hash VARCHAR(64) NOT NULL,
  content BYTEA NOT NULL,
  uploaded_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT source_size CHECK (octet_length(content) <= 26214400)
);
CREATE TABLE IF NOT EXISTS intelligence_hub.analytics_events (
  id VARCHAR(64) PRIMARY KEY,
  event_type VARCHAR(128) NOT NULL,
  conversation_message_id VARCHAR(64),
  workflow_version_id VARCHAR(64),
  payload JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_reference_documents_dept_status ON knowledge_studio.reference_documents (department_id, status);
CREATE INDEX IF NOT EXISTS ix_reference_chunks_dept_doc ON knowledge_studio.reference_chunks (department_id, document_id);
CREATE INDEX IF NOT EXISTS ix_knowledge_workflow_versions ON knowledge_studio.workflow_versions (workflow_id, status, version_number);
CREATE INDEX IF NOT EXISTS ix_conversation_owner ON workmate_copilot.conversations (user_id, started_at DESC);
CREATE INDEX IF NOT EXISTS ix_workflow_search_scope ON knowledge_studio.workflow_search_metadata (department_id, status);
CREATE INDEX IF NOT EXISTS ix_source_owner ON shared.source_objects (department_id);
