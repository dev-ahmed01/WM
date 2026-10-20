-- Phase 4A: one durable operational exception per blocked task, never a release authorization.
CREATE TABLE IF NOT EXISTS workmate_copilot.work_exceptions (
  id VARCHAR(64) PRIMARY KEY,
  department_id VARCHAR(64) NOT NULL REFERENCES security.departments(id),
  work_item_id VARCHAR(64) NOT NULL UNIQUE REFERENCES workmate_copilot.work_items(id),
  execution_session_id VARCHAR(64) NOT NULL REFERENCES workmate_copilot.workflow_sessions(id),
  raised_by VARCHAR(64) NOT NULL REFERENCES security.users(id),
  trigger VARCHAR(24) NOT NULL CHECK (trigger IN ('worker_report','sop_outcome')),
  severity VARCHAR(16) NOT NULL CHECK (severity IN ('high','critical')),
  reason VARCHAR(500) NOT NULL,
  state_id VARCHAR(64) NULL REFERENCES knowledge_studio.workflow_states(id),
  decision_option VARCHAR(128) NULL,
  status VARCHAR(24) NOT NULL DEFAULT 'open'
    CHECK (status IN ('open','claimed','follow_up_requested','reviewed')),
  reviewer_id VARCHAR(64) NULL REFERENCES security.users(id),
  review_note VARCHAR(1000) NULL,
  revision INT NOT NULL DEFAULT 1 CHECK(revision>=1),
  created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  reviewed_at TIMESTAMPTZ NULL,
  CONSTRAINT work_exception_review_consistency CHECK (
    (status IN ('open','claimed') AND reviewed_at IS NULL)
    OR (status IN ('follow_up_requested','reviewed') AND reviewed_at IS NOT NULL)
  )
);
CREATE INDEX IF NOT EXISTS ix_work_exceptions_queue
  ON workmate_copilot.work_exceptions(department_id,status,created_at DESC);
CREATE INDEX IF NOT EXISTS ix_work_exceptions_reviewer
  ON workmate_copilot.work_exceptions(reviewer_id,created_at DESC);

CREATE TABLE IF NOT EXISTS workmate_copilot.work_exception_events (
  id VARCHAR(64) PRIMARY KEY,
  case_id VARCHAR(64) NOT NULL REFERENCES workmate_copilot.work_exceptions(id),
  department_id VARCHAR(64) NOT NULL REFERENCES security.departments(id),
  actor_id VARCHAR(64) NOT NULL REFERENCES security.users(id),
  action VARCHAR(24) NOT NULL CHECK (action IN ('opened','claimed','follow_up_requested','reviewed')),
  note VARCHAR(1000) NOT NULL DEFAULT '',
  event_seq BIGINT GENERATED ALWAYS AS IDENTITY,
  created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_exception_events_case
  ON workmate_copilot.work_exception_events(case_id,event_seq);

ALTER TABLE workmate_copilot.work_item_events
 DROP CONSTRAINT IF EXISTS work_item_events_action_check;
ALTER TABLE workmate_copilot.work_item_events
 ADD CONSTRAINT work_item_events_action_check CHECK (
    action IN ('created','assigned','bound','started','step_recorded','decision_recorded',
               'state_advanced','paused','resumed','blocked','completed','exception_claimed',
               'exception_reviewed','exception_follow_up')
 );

ALTER TABLE workmate_copilot.work_exceptions ENABLE ROW LEVEL SECURITY;
ALTER TABLE workmate_copilot.work_exception_events ENABLE ROW LEVEL SECURITY;
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_policies
    WHERE schemaname='workmate_copilot' AND tablename='work_exceptions'
      AND policyname='wm_work_exception_scope') THEN
    CREATE POLICY wm_work_exception_scope ON workmate_copilot.work_exceptions FOR ALL TO PUBLIC
      USING (department_id=NULLIF(current_setting('workmate.department_id',true),''))
      WITH CHECK (department_id=NULLIF(current_setting('workmate.department_id',true),''));
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_policies
    WHERE schemaname='workmate_copilot' AND tablename='work_exception_events'
      AND policyname='wm_work_exception_events_scope') THEN
    CREATE POLICY wm_work_exception_events_scope ON workmate_copilot.work_exception_events FOR ALL TO PUBLIC
      USING (department_id=NULLIF(current_setting('workmate.department_id',true),''))
      WITH CHECK (department_id=NULLIF(current_setting('workmate.department_id',true),''));
  END IF;
END $$;
GRANT SELECT ON workmate_copilot.work_exceptions,
 workmate_copilot.work_exception_events TO workmate_scoped_reader;
