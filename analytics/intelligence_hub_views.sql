-- ============================================================================
-- WorkMate AI — Intelligence Hub BI Materialized Views (OWD Execution Analytics)
-- ============================================================================

-- 1. SOP / OWD Usage View
CREATE OR REPLACE VIEW V_ANALYTICS_SOP_USAGE AS
SELECT 
    w.id AS sop_id,
    w.title AS sop_title,
    w.department_id,
    COUNT(DISTINCT s.id) AS total_executions,
    COUNT(DISTINCT s.user_id) AS unique_users,
    AVG(DATEDIFF('second', s.started_at, COALESCE(s.completed_at, CURRENT_TIMESTAMP())) / 60.0) AS avg_completion_minutes,
    MAX(s.updated_at) AS last_used_at
FROM KNOWLEDGE_STUDIO.workflows w
LEFT JOIN KNOWLEDGE_STUDIO.workflow_versions v ON w.id = v.workflow_id
LEFT JOIN WORKMATE_COPILOT.workflow_sessions s ON v.id = s.workflow_version_id
GROUP BY w.id, w.title, w.department_id;

-- 2. Confusing Procedures & Bottleneck View
CREATE OR REPLACE VIEW V_ANALYTICS_CONFUSING_PROCEDURES AS
SELECT 
    w.id AS sop_id,
    w.title AS sop_title,
    w.department_id,
    COUNT(DISTINCT s.id) AS total_sessions,
    COUNT(DISTINCT CASE WHEN s.status IN ('escalated', 'abandoned') THEN s.id END) AS confusing_sessions,
    ROUND(
        COUNT(DISTINCT CASE WHEN s.status IN ('escalated', 'abandoned') THEN s.id END) * 100.0 / NULLIF(COUNT(DISTINCT s.id), 0), 
        2
    ) AS confusion_rate_pct,
    COUNT(DISTINCT e.id) AS total_escalations
FROM KNOWLEDGE_STUDIO.workflows w
LEFT JOIN KNOWLEDGE_STUDIO.workflow_versions v ON w.id = v.workflow_id
LEFT JOIN WORKMATE_COPILOT.workflow_sessions s ON v.id = s.workflow_version_id
LEFT JOIN WORKMATE_COPILOT.escalation_records e ON s.id = e.session_id
GROUP BY w.id, w.title, w.department_id;

-- 3. Department Adoption View
CREATE OR REPLACE VIEW V_ANALYTICS_DEPARTMENT_ADOPTION AS
SELECT 
    d.id AS department_id,
    d.name AS department_name,
    COUNT(DISTINCT u.id) AS total_users,
    COUNT(DISTINCT s.id) AS total_workflow_runs,
    COUNT(DISTINCT CASE WHEN s.status = 'completed' THEN s.id END) AS completed_runs,
    ROUND(
        COUNT(DISTINCT CASE WHEN s.status = 'completed' THEN s.id END) * 100.0 / NULLIF(COUNT(DISTINCT s.id), 0),
        2
    ) AS completion_rate_pct
FROM SECURITY.departments d
LEFT JOIN SECURITY.users u ON d.id = u.department_id
LEFT JOIN WORKMATE_COPILOT.workflow_sessions s ON u.id = s.user_id
GROUP BY d.id, d.name;

-- 4. Escalations Heatmap View
CREATE OR REPLACE VIEW V_ANALYTICS_ESCALATIONS AS
SELECT 
    e.id AS escalation_id,
    e.session_id,
    e.reason,
    e.status,
    e.created_at,
    s.user_id,
    w.title AS workflow_title,
    w.department_id
FROM WORKMATE_COPILOT.escalation_records e
JOIN WORKMATE_COPILOT.workflow_sessions s ON e.session_id = s.id
JOIN KNOWLEDGE_STUDIO.workflow_versions v ON s.workflow_version_id = v.id
JOIN KNOWLEDGE_STUDIO.workflows w ON v.workflow_id = w.id;

-- 5. FAQs View
CREATE OR REPLACE VIEW V_ANALYTICS_FAQS AS
SELECT 
    m.intent AS query_intent,
    COUNT(m.id) AS query_count,
    AVG(m.confidence_score) AS avg_confidence,
    COUNT(CASE WHEN m.escalated THEN 1 END) AS escalation_count
FROM WORKMATE_COPILOT.conversation_messages m
WHERE m.sender = 'employee' AND m.intent IS NOT NULL
GROUP BY m.intent;

-- 6. Confidence Trends View
CREATE OR REPLACE VIEW V_ANALYTICS_CONFIDENCE_TRENDS AS
SELECT 
    DATE_TRUNC('day', created_at) AS event_date,
    AVG(confidence_score) AS mean_confidence_score,
    COUNT(id) AS total_queries,
    COUNT(CASE WHEN escalated THEN 1 END) AS escalated_queries
FROM WORKMATE_COPILOT.conversation_messages
WHERE sender = 'ai'
GROUP BY DATE_TRUNC('day', created_at);
