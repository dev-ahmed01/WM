-- 09_owd_v1_1_tables.sql: OWD v1.1 Schema Expansion for KNOWLEDGE_STUDIO

-- 1. Extend KNOWLEDGE_STUDIO.workflows table
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

-- 2. Extend KNOWLEDGE_STUDIO.workflow_states table
ALTER TABLE KNOWLEDGE_STUDIO.workflow_states ADD COLUMN IF NOT EXISTS purpose TEXT NULL;
ALTER TABLE KNOWLEDGE_STUDIO.workflow_states ADD COLUMN IF NOT EXISTS entry_condition TEXT NULL;
ALTER TABLE KNOWLEDGE_STUDIO.workflow_states ADD COLUMN IF NOT EXISTS exit_condition TEXT NULL;
ALTER TABLE KNOWLEDGE_STUDIO.workflow_states ADD COLUMN IF NOT EXISTS responsible_role VARCHAR(128) NULL;
ALTER TABLE KNOWLEDGE_STUDIO.workflow_states ADD COLUMN IF NOT EXISTS expected_duration VARCHAR(64) NULL;
ALTER TABLE KNOWLEDGE_STUDIO.workflow_states ADD COLUMN IF NOT EXISTS business_objective TEXT NULL;

-- 3. Extend KNOWLEDGE_STUDIO.workflow_steps table
ALTER TABLE KNOWLEDGE_STUDIO.workflow_steps ADD COLUMN IF NOT EXISTS sequence_number INT NULL;
ALTER TABLE KNOWLEDGE_STUDIO.workflow_steps ADD COLUMN IF NOT EXISTS safety_note TEXT NULL;
ALTER TABLE KNOWLEDGE_STUDIO.workflow_steps ADD COLUMN IF NOT EXISTS estimated_time VARCHAR(64) NULL;
ALTER TABLE KNOWLEDGE_STUDIO.workflow_steps ADD COLUMN IF NOT EXISTS retry_policy VARCHAR(255) NULL;
ALTER TABLE KNOWLEDGE_STUDIO.workflow_steps ADD COLUMN IF NOT EXISTS completion_criteria TEXT NULL;
ALTER TABLE KNOWLEDGE_STUDIO.workflow_steps ADD COLUMN IF NOT EXISTS common_failure TEXT NULL;
ALTER TABLE KNOWLEDGE_STUDIO.workflow_steps ADD COLUMN IF NOT EXISTS recovery_action TEXT NULL;

-- 4. Create KNOWLEDGE_STUDIO.workflow_decisions
CREATE TABLE IF NOT EXISTS KNOWLEDGE_STUDIO.workflow_decisions (
    id VARCHAR(64) PRIMARY KEY,
    state_id VARCHAR(64) NOT NULL REFERENCES KNOWLEDGE_STUDIO.workflow_states(id),
    decision_code VARCHAR(128) NOT NULL,
    question TEXT NOT NULL,
    alternative_path TEXT NULL,
    business_rule TEXT NULL,
    escalation_workflow VARCHAR(128) NULL
);

-- 5. Create KNOWLEDGE_STUDIO.workflow_ai_conversation
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

-- 6. Create KNOWLEDGE_STUDIO.workflow_analytics
CREATE TABLE IF NOT EXISTS KNOWLEDGE_STUDIO.workflow_analytics (
    id VARCHAR(64) PRIMARY KEY,
    workflow_version_id VARCHAR(64) NOT NULL REFERENCES KNOWLEDGE_STUDIO.workflow_versions(id),
    event_name VARCHAR(128) NOT NULL,
    event_trigger VARCHAR(128) NOT NULL,
    kpis TEXT NULL
);

-- 7. Create KNOWLEDGE_STUDIO.workflow_relationships
CREATE TABLE IF NOT EXISTS KNOWLEDGE_STUDIO.workflow_relationships (
    id VARCHAR(64) PRIMARY KEY,
    workflow_version_id VARCHAR(64) NOT NULL REFERENCES KNOWLEDGE_STUDIO.workflow_versions(id),
    relationship_type VARCHAR(64) NOT NULL CHECK (relationship_type IN ('PARENT_SOP', 'CHILD_SOP', 'RELATED_SOP', 'PREVIOUS_SOP', 'NEXT_SOP', 'ESCALATION_SOP', 'EXCEPTION_SOP', 'REFERENCED_EQUIPMENT', 'REFERENCED_DOCUMENT', 'REFERENCED_POLICY')),
    target_reference VARCHAR(512) NOT NULL,
    description TEXT NULL
);

-- 8. Create KNOWLEDGE_STUDIO.workflow_references
CREATE TABLE IF NOT EXISTS KNOWLEDGE_STUDIO.workflow_references (
    id VARCHAR(64) PRIMARY KEY,
    workflow_version_id VARCHAR(64) NOT NULL REFERENCES KNOWLEDGE_STUDIO.workflow_versions(id),
    reference_type VARCHAR(64) NOT NULL CHECK (reference_type IN ('PRIMARY_SOURCE', 'SUPPORTING_SOURCE', 'OFFICIAL_URL', 'COMPLIANCE_STANDARD', 'DOC_SECTION')),
    title VARCHAR(512) NOT NULL,
    citation_uri TEXT NOT NULL
);

-- 9. Create KNOWLEDGE_STUDIO.workflow_role_permissions
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
