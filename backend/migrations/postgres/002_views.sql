-- PostgreSQL-native, read-only analytics views for existing Manager UI.
-- These derive solely from persisted events. Empty populations yield zeros/nulls.
CREATE OR REPLACE VIEW intelligence_hub.v_analytics_sop_usage AS
SELECT w.id AS sop_id, w.title AS sop_title, w.department_id,
       COUNT(DISTINCT s.id) AS total_executions,
       COUNT(DISTINCT s.user_id) AS unique_users,
       AVG(EXTRACT(EPOCH FROM (COALESCE(s.completed_at, CURRENT_TIMESTAMP) - s.started_at)) / 60)
           FILTER (WHERE s.id IS NOT NULL) AS avg_completion_minutes,
       MAX(s.updated_at) AS last_used_at
FROM knowledge_studio.workflows w
LEFT JOIN knowledge_studio.workflow_versions v ON v.workflow_id = w.id
LEFT JOIN workmate_copilot.workflow_sessions s ON s.workflow_version_id = v.id
GROUP BY w.id, w.title, w.department_id;

CREATE OR REPLACE VIEW intelligence_hub.v_analytics_confusing_procedures AS
SELECT w.id AS sop_id, w.title AS sop_title, w.department_id,
       COUNT(DISTINCT s.id) AS total_sessions,
       COUNT(DISTINCT s.id) FILTER (WHERE s.status IN ('escalated','abandoned')) AS confusing_sessions,
       ROUND(100.0 * COUNT(DISTINCT s.id) FILTER (WHERE s.status IN ('escalated','abandoned'))
             / NULLIF(COUNT(DISTINCT s.id),0),2) AS confusion_rate_pct,
       COUNT(DISTINCT e.id) AS total_escalations
FROM knowledge_studio.workflows w
LEFT JOIN knowledge_studio.workflow_versions v ON v.workflow_id = w.id
LEFT JOIN workmate_copilot.workflow_sessions s ON s.workflow_version_id = v.id
LEFT JOIN workmate_copilot.escalation_records e ON e.session_id = s.id
GROUP BY w.id,w.title,w.department_id;

CREATE OR REPLACE VIEW intelligence_hub.v_analytics_department_adoption AS
SELECT d.id AS department_id,
       COUNT(DISTINCT u.id) AS total_enrolled_users,
       COUNT(DISTINCT c.user_id) AS active_copilot_users,
       COUNT(DISTINCT m.id) AS total_interactions,
       ROUND(100.0 * COUNT(DISTINCT c.user_id) / NULLIF(COUNT(DISTINCT u.id),0),2) AS adoption_rate_pct
FROM security.departments d
LEFT JOIN security.users u ON u.department_id=d.id AND COALESCE(u.status,'active')='active'
LEFT JOIN workmate_copilot.conversations c ON c.user_id=u.id
LEFT JOIN workmate_copilot.conversation_messages m ON m.conversation_id=c.id
WHERE COALESCE(d.is_active,true)
GROUP BY d.id;

CREATE OR REPLACE VIEW intelligence_hub.v_analytics_escalations AS
SELECT e.id AS escalation_id, e.session_id, COALESCE(s.user_id,c.user_id) AS user_id,
       COALESCE(w.department_id,c.department_id) AS department_id,
       w.id AS sop_id, w.title AS sop_title, e.reason AS escalation_reason,
       e.status AS escalation_status, e.created_at
FROM workmate_copilot.escalation_records e
LEFT JOIN workmate_copilot.workflow_sessions s ON s.id=e.session_id
LEFT JOIN knowledge_studio.workflow_versions v ON v.id=s.workflow_version_id
LEFT JOIN knowledge_studio.workflows w ON w.id=v.workflow_id
LEFT JOIN workmate_copilot.conversation_messages cm ON cm.id=e.conversation_message_id
LEFT JOIN workmate_copilot.conversations c ON c.id=cm.conversation_id;

CREATE OR REPLACE VIEW intelligence_hub.v_analytics_faqs AS
SELECT m.intent AS query_topic, c.department_id, COUNT(*) AS query_count,
       NULL::double precision AS avg_confidence, MAX(m.created_at) AS last_queried_at
FROM workmate_copilot.conversation_messages m
JOIN workmate_copilot.conversations c ON c.id=m.conversation_id
WHERE m.sender='employee' AND m.intent IS NOT NULL
GROUP BY m.intent,c.department_id;

CREATE OR REPLACE VIEW intelligence_hub.v_analytics_confidence_trends AS
SELECT DATE_TRUNC('day',m.created_at) AS metric_date, c.department_id,
       COUNT(*) AS total_responses, AVG(m.confidence_score) AS avg_confidence_score,
       MIN(m.confidence_score) AS min_confidence_score,
       MAX(m.confidence_score) AS max_confidence_score
FROM workmate_copilot.conversation_messages m
JOIN workmate_copilot.conversations c ON c.id=m.conversation_id
WHERE m.sender='ai'
GROUP BY DATE_TRUNC('day',m.created_at),c.department_id;

CREATE OR REPLACE VIEW intelligence_hub.v_analytics_voice_usage AS
SELECT original_language AS language, COUNT(*) AS voice_interaction_count,
       COUNT(*) FILTER (WHERE success) AS successful_transcriptions,
       ROUND(100.0 * COUNT(*) FILTER (WHERE success) / NULLIF(COUNT(*),0),2) AS transcription_success_rate_pct,
       AVG(translation_ms) AS avg_translation_latency_ms,
       AVG(transcription_ms) AS avg_transcription_latency_ms,
       AVG(synthesis_ms) AS avg_synthesis_latency_ms,
       MAX(created_at) AS last_used_at
FROM workmate_copilot.voice_interactions GROUP BY original_language;
