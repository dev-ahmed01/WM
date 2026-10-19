-- Phase 2 uses the existing published OWD graph and workflow_sessions.
-- Every task can have exactly one bound SOP version and one owned execution session.
ALTER TABLE workmate_copilot.work_items
  ADD COLUMN IF NOT EXISTS workflow_version_id VARCHAR(64) NULL REFERENCES knowledge_studio.workflow_versions(id),
  ADD COLUMN IF NOT EXISTS execution_session_id VARCHAR(64) NULL REFERENCES workmate_copilot.workflow_sessions(id),
  ADD COLUMN IF NOT EXISTS completed_at TIMESTAMPTZ NULL;
ALTER TABLE workmate_copilot.work_items DROP CONSTRAINT IF EXISTS work_items_status_check;
ALTER TABLE workmate_copilot.work_items ADD CONSTRAINT work_items_status_check CHECK
  (status IN ('queued','ready','active','paused','blocked','completed'));
ALTER TABLE workmate_copilot.work_items DROP CONSTRAINT IF EXISTS work_items_execution_state_check;
ALTER TABLE workmate_copilot.work_items ADD CONSTRAINT work_items_execution_state_check CHECK (
    (status = 'queued' AND workflow_version_id IS NULL AND execution_session_id IS NULL)
    OR (status = 'ready' AND workflow_version_id IS NOT NULL AND execution_session_id IS NULL)
    OR (status IN ('active','paused','blocked','completed')
        AND workflow_version_id IS NOT NULL AND execution_session_id IS NOT NULL)
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_work_item_execution
    ON workmate_copilot.work_items(execution_session_id)
    WHERE execution_session_id IS NOT NULL;

ALTER TABLE workmate_copilot.work_item_events
  ADD COLUMN IF NOT EXISTS event_payload JSONB NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE workmate_copilot.work_item_events
  DROP CONSTRAINT IF EXISTS work_item_events_action_check;
ALTER TABLE workmate_copilot.work_item_events
  ADD CONSTRAINT work_item_events_action_check CHECK (
    action IN ('created','bound','started','step_recorded','decision_recorded',
               'paused','resumed','blocked','completed')
  );
CREATE INDEX IF NOT EXISTS ix_work_item_events_dept_time
  ON workmate_copilot.work_item_events(department_id, created_at DESC);
