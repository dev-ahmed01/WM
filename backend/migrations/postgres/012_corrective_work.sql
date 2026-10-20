-- Phase 4C: independent authorization of NEW corrective work, never re-entry
-- into a blocked task's immutable evidence or stopped execution session.
CREATE TABLE IF NOT EXISTS workmate_copilot.work_corrective_requests (
  id VARCHAR(64) PRIMARY KEY,
  department_id VARCHAR(64) NOT NULL REFERENCES security.departments(id),
  case_id VARCHAR(64) NOT NULL UNIQUE REFERENCES workmate_copilot.work_exceptions(id),
  proposed_by VARCHAR(64) NOT NULL REFERENCES security.users(id),
  proposed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  workflow_version_id VARCHAR(64) NOT NULL REFERENCES knowledge_studio.workflow_versions(id),
  assigned_to VARCHAR(64) NOT NULL REFERENCES security.users(id),
  plan_note VARCHAR(1000) NOT NULL,
  status VARCHAR(16) NOT NULL DEFAULT 'pending'
    CHECK (status IN ('pending','approved','rejected')),
  decided_by VARCHAR(64) NULL REFERENCES security.users(id),
  decision_note VARCHAR(1000) NULL,
  decided_at TIMESTAMPTZ NULL,
  corrective_work_id VARCHAR(64) NULL UNIQUE REFERENCES workmate_copilot.work_items(id),
  CONSTRAINT corrective_request_decision_consistency CHECK (
    (status='pending' AND decided_by IS NULL AND decided_at IS NULL
      AND decision_note IS NULL AND corrective_work_id IS NULL)
    OR
    (status='rejected' AND decided_by IS NOT NULL AND decided_at IS NOT NULL
      AND decision_note IS NOT NULL AND corrective_work_id IS NULL)
    OR
    (status='approved' AND decided_by IS NOT NULL AND decided_at IS NOT NULL
      AND decision_note IS NOT NULL AND corrective_work_id IS NOT NULL)
  ),
  CONSTRAINT corrective_request_independent_approval CHECK (
     decided_by IS NULL OR decided_by<>proposed_by
  )
);
CREATE INDEX IF NOT EXISTS ix_work_corrective_requests_department_status
  ON workmate_copilot.work_corrective_requests(department_id,status,proposed_at);

ALTER TABLE workmate_copilot.work_exception_events
 DROP CONSTRAINT IF EXISTS work_exception_events_action_check;
ALTER TABLE workmate_copilot.work_exception_events
 ADD CONSTRAINT work_exception_events_action_check CHECK (
  action IN ('opened','claimed','follow_up_requested','reviewed',
             'containment_recorded','remediation_proposed','handover_linked',
             'corrective_requested','corrective_approved','corrective_rejected')
 );

ALTER TABLE workmate_copilot.work_item_events
 DROP CONSTRAINT IF EXISTS work_item_events_action_check;
ALTER TABLE workmate_copilot.work_item_events
 ADD CONSTRAINT work_item_events_action_check CHECK (
    action IN ('created','assigned','bound','started','step_recorded','decision_recorded',
               'state_advanced','paused','resumed','blocked','completed','exception_claimed',
               'exception_reviewed','exception_follow_up',
               'containment_recorded','remediation_proposed','handover_linked',
               'corrective_requested','corrective_approved','corrective_rejected')
 );

ALTER TABLE workmate_copilot.work_corrective_requests ENABLE ROW LEVEL SECURITY;
DO $$
BEGIN
  IF NOT EXISTS(SELECT 1 FROM pg_policies
    WHERE schemaname='workmate_copilot' AND tablename='work_corrective_requests'
    AND policyname='wm_corrective_requests_dept') THEN
    CREATE POLICY wm_corrective_requests_dept
      ON workmate_copilot.work_corrective_requests FOR ALL TO PUBLIC
      USING (department_id=NULLIF(current_setting('workmate.department_id',true),''))
      WITH CHECK (department_id=NULLIF(current_setting('workmate.department_id',true),''));
  END IF;
END $$;
GRANT SELECT ON workmate_copilot.work_corrective_requests TO workmate_scoped_reader;
