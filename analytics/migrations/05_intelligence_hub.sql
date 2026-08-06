-- 05_intelligence_hub.sql: Create INTELLIGENCE_HUB schema telemetry table

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
