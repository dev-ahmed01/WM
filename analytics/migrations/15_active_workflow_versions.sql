-- Keep exactly one active published version per workflow and align its
-- department-scoped retrieval metadata with the canonical workflow record.

UPDATE KNOWLEDGE_STUDIO.workflow_versions
SET status = 'deprecated'
WHERE id IN (
    SELECT id
    FROM KNOWLEDGE_STUDIO.workflow_versions
    WHERE LOWER(status) = 'published'
    QUALIFY ROW_NUMBER() OVER (
        PARTITION BY workflow_id
        ORDER BY version_number DESC, published_at DESC, created_at DESC, id DESC
    ) > 1
);

UPDATE KNOWLEDGE_STUDIO.workflow_search_metadata AS metadata
SET status = 'archived'
FROM KNOWLEDGE_STUDIO.workflow_versions AS version
WHERE metadata.workflow_version_id = version.id
  AND LOWER(version.status) = 'deprecated'
  AND LOWER(metadata.status) = 'published';

UPDATE KNOWLEDGE_STUDIO.workflow_search_metadata AS metadata
SET department_id = workflow.department_id
FROM KNOWLEDGE_STUDIO.workflow_versions AS version
JOIN KNOWLEDGE_STUDIO.workflows AS workflow
  ON workflow.id = version.workflow_id
WHERE metadata.workflow_version_id = version.id
  AND LOWER(version.status) = 'published'
  AND metadata.department_id <> workflow.department_id;
