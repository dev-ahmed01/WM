-- Align runtime audit columns and Intelligence Hub views with backend queries.

ALTER TABLE SHARED.audit_logs
    ADD COLUMN IF NOT EXISTS role VARCHAR(64) DEFAULT 'UNKNOWN';

ALTER TABLE SHARED.audit_logs
    ADD COLUMN IF NOT EXISTS status_code INT DEFAULT 0;

CREATE OR REPLACE VIEW INTELLIGENCE_HUB.V_ANALYTICS_SOP_USAGE AS
SELECT
    w.id AS sop_id,
    w.title AS sop_title,
    w.department_id,
    COUNT(DISTINCT s.id) AS total_executions,
    COUNT(DISTINCT s.user_id) AS unique_users,
    AVG(DATEDIFF('second', s.started_at, COALESCE(s.completed_at, CURRENT_TIMESTAMP())) / 60.0)
        AS avg_completion_minutes,
    MAX(s.updated_at) AS last_used_at
FROM KNOWLEDGE_STUDIO.workflows w
LEFT JOIN KNOWLEDGE_STUDIO.workflow_versions v ON v.workflow_id = w.id
LEFT JOIN WORKMATE_COPILOT.workflow_sessions s ON s.workflow_version_id = v.id
GROUP BY w.id, w.title, w.department_id;

CREATE OR REPLACE VIEW INTELLIGENCE_HUB.V_ANALYTICS_CONFUSING_PROCEDURES AS
SELECT
    w.id AS sop_id,
    w.title AS sop_title,
    w.department_id,
    COUNT(DISTINCT s.id) AS total_sessions,
    COUNT(DISTINCT CASE WHEN s.status IN ('escalated', 'abandoned') THEN s.id END)
        AS confusing_sessions,
    ROUND(
        COUNT(DISTINCT CASE WHEN s.status IN ('escalated', 'abandoned') THEN s.id END)
        * 100.0 / NULLIF(COUNT(DISTINCT s.id), 0),
        2
    ) AS confusion_rate_pct,
    COUNT(DISTINCT e.id) AS total_escalations
FROM KNOWLEDGE_STUDIO.workflows w
LEFT JOIN KNOWLEDGE_STUDIO.workflow_versions v ON v.workflow_id = w.id
LEFT JOIN WORKMATE_COPILOT.workflow_sessions s ON s.workflow_version_id = v.id
LEFT JOIN WORKMATE_COPILOT.escalation_records e ON e.session_id = s.id
GROUP BY w.id, w.title, w.department_id;

CREATE OR REPLACE VIEW INTELLIGENCE_HUB.V_ANALYTICS_DEPARTMENT_ADOPTION AS
SELECT
    d.id AS department_id,
    COUNT(DISTINCT u.id) AS total_enrolled_users,
    COUNT(DISTINCT c.user_id) AS active_copilot_users,
    COUNT(DISTINCT m.id) AS total_interactions,
    ROUND(
        COUNT(DISTINCT c.user_id) * 100.0 / NULLIF(COUNT(DISTINCT u.id), 0),
        2
    ) AS adoption_rate_pct
FROM SECURITY.departments d
LEFT JOIN SECURITY.users u
  ON u.department_id = d.id AND LOWER(COALESCE(u.status, 'active')) = 'active'
LEFT JOIN WORKMATE_COPILOT.conversations c ON c.user_id = u.id
LEFT JOIN WORKMATE_COPILOT.conversation_messages m ON m.conversation_id = c.id
WHERE COALESCE(d.is_active, TRUE) = TRUE
GROUP BY d.id;

CREATE OR REPLACE VIEW INTELLIGENCE_HUB.V_ANALYTICS_ESCALATIONS AS
SELECT
    e.id AS escalation_id,
    e.session_id,
    COALESCE(s.user_id, c.user_id) AS user_id,
    COALESCE(w.department_id, c.department_id) AS department_id,
    w.id AS sop_id,
    w.title AS sop_title,
    e.reason AS escalation_reason,
    e.status AS escalation_status,
    e.created_at
FROM WORKMATE_COPILOT.escalation_records e
LEFT JOIN WORKMATE_COPILOT.workflow_sessions s ON s.id = e.session_id
LEFT JOIN KNOWLEDGE_STUDIO.workflow_versions v ON v.id = s.workflow_version_id
LEFT JOIN KNOWLEDGE_STUDIO.workflows w ON w.id = v.workflow_id
LEFT JOIN WORKMATE_COPILOT.conversation_messages cm
  ON cm.id = e.conversation_message_id
LEFT JOIN WORKMATE_COPILOT.conversations c ON c.id = cm.conversation_id;

CREATE OR REPLACE VIEW INTELLIGENCE_HUB.V_ANALYTICS_FAQS AS
SELECT
    m.intent AS query_topic,
    c.department_id,
    COUNT(*) AS query_count,
    CAST(NULL AS FLOAT) AS avg_confidence,
    MAX(m.created_at) AS last_queried_at
FROM WORKMATE_COPILOT.conversation_messages m
JOIN WORKMATE_COPILOT.conversations c ON c.id = m.conversation_id
WHERE m.sender = 'employee' AND m.intent IS NOT NULL
GROUP BY m.intent, c.department_id;

CREATE OR REPLACE VIEW INTELLIGENCE_HUB.V_ANALYTICS_CONFIDENCE_TRENDS AS
SELECT
    DATE_TRUNC('day', m.created_at) AS metric_date,
    c.department_id,
    COUNT(*) AS total_responses,
    AVG(m.confidence_score) AS avg_confidence_score,
    MIN(m.confidence_score) AS min_confidence_score,
    MAX(m.confidence_score) AS max_confidence_score
FROM WORKMATE_COPILOT.conversation_messages m
JOIN WORKMATE_COPILOT.conversations c ON c.id = m.conversation_id
WHERE m.sender = 'ai'
GROUP BY DATE_TRUNC('day', m.created_at), c.department_id;
