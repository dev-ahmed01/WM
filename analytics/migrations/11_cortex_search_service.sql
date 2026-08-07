-- 11_cortex_search_service.sql
-- Semantic + lexical index over the single, authoritative OWD compiler output.
-- Run with a role that can create Cortex Search services in KNOWLEDGE_STUDIO.

CREATE OR REPLACE CORTEX SEARCH SERVICE KNOWLEDGE_STUDIO.WORKMATE_KNOWLEDGE_SEARCH
    ON search_content
    PRIMARY KEY (chunk_id)
    ATTRIBUTES department_id, status
    WAREHOUSE = COMPUTE_WH
    TARGET_LAG = '1 minute'
AS
SELECT
    sm.id AS chunk_id,
    w.id AS document_id,
    w.title AS document_title,
    wv.version_number AS version_number,
    s.id AS state_id,
    s.ordinal_index + 1 AS step_number,
    s.title AS step_title,
    sm.search_content AS search_content,
    sm.department_id AS department_id,
    LOWER(wv.status) AS status
FROM KNOWLEDGE_STUDIO.workflow_search_metadata sm
JOIN KNOWLEDGE_STUDIO.workflow_versions wv
  ON sm.workflow_version_id = wv.id
JOIN KNOWLEDGE_STUDIO.workflows w
  ON wv.workflow_id = w.id
JOIN KNOWLEDGE_STUDIO.workflow_states s
  ON sm.state_id = s.id
WHERE LOWER(sm.status) = 'published'
  AND LOWER(wv.status) IN ('published', 'compiled');

-- Cortex features also require account privileges. An ACCOUNTADMIN can grant:
-- GRANT DATABASE ROLE SNOWFLAKE.CORTEX_USER TO ROLE <WORKMATE_BACKEND_ROLE>;
-- GRANT USAGE ON CORTEX SEARCH SERVICE
--   WORKMATE_AI.KNOWLEDGE_STUDIO.WORKMATE_KNOWLEDGE_SEARCH
--   TO ROLE <WORKMATE_BACKEND_ROLE>;
