-- Phase 6A: department-scoped WMS/ERP event intake. Nothing created as
-- executable work before a separate human reviewer accepts the staged record.
CREATE TABLE IF NOT EXISTS workmate_copilot.work_integration_intake (
  id VARCHAR(64) PRIMARY KEY,
  department_id VARCHAR(64) NOT NULL REFERENCES security.departments(id),
  source_system VARCHAR(24) NOT NULL CHECK (source_system IN ('sap','oracle','odoo','custom_wms')),
  external_event_id VARCHAR(100) NOT NULL,
  external_work_id VARCHAR(100) NOT NULL,
  payload_digest CHAR(64) NOT NULL CHECK (payload_digest ~ '^[0-9a-f]{64}$'),
  normalized_payload JSONB NOT NULL,
  submitted_by VARCHAR(64) NOT NULL REFERENCES security.users(id),
  status VARCHAR(16) NOT NULL DEFAULT 'pending'
    CHECK(status IN ('pending','accepted','rejected')),
  decided_by VARCHAR(64) NULL REFERENCES security.users(id),
  decision_note VARCHAR(1000) NULL,
  decided_at TIMESTAMPTZ NULL,
  work_item_id VARCHAR(64) NULL UNIQUE REFERENCES workmate_copilot.work_items(id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT wm_intake_unique_event UNIQUE(department_id,source_system,external_event_id),
  CONSTRAINT wm_intake_unique_work UNIQUE(department_id,source_system,external_work_id),
  CONSTRAINT wm_intake_separate_reviewer CHECK(decided_by IS NULL OR decided_by<>submitted_by),
  CONSTRAINT wm_intake_payload_object CHECK(jsonb_typeof(normalized_payload)='object'),
  CONSTRAINT wm_intake_decision_consistency CHECK(
    (status='pending' AND decided_by IS NULL AND decision_note IS NULL
      AND decided_at IS NULL AND work_item_id IS NULL)
    OR (status='rejected' AND decided_by IS NOT NULL AND decision_note IS NOT NULL
      AND decided_at IS NOT NULL AND work_item_id IS NULL)
    OR (status='accepted' AND decided_by IS NOT NULL AND decision_note IS NOT NULL
      AND decided_at IS NOT NULL AND work_item_id IS NOT NULL)
  )
);
CREATE INDEX IF NOT EXISTS ix_work_intake_dept_pending
  ON workmate_copilot.work_integration_intake(department_id,status,created_at DESC);

ALTER TABLE workmate_copilot.work_item_events
  DROP CONSTRAINT IF EXISTS work_item_events_action_check;
ALTER TABLE workmate_copilot.work_item_events
  ADD CONSTRAINT work_item_events_action_check CHECK (
    action IN ('created','assigned','bound','started','step_recorded','decision_recorded',
               'state_advanced','paused','resumed','blocked','completed','exception_claimed',
               'exception_reviewed','exception_follow_up',
               'containment_recorded','remediation_proposed','handover_linked',
               'corrective_requested','corrective_approved','corrective_rejected',
               'evidence_reviewed','site_accepted','case_closed','integration_imported')
  );
ALTER TABLE workmate_copilot.work_integration_intake ENABLE ROW LEVEL SECURITY;
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname='workmate_copilot'
    AND tablename='work_integration_intake'
    AND policyname='wm_work_integration_dept') THEN
      CREATE POLICY wm_work_integration_dept ON workmate_copilot.work_integration_intake
        FOR ALL TO PUBLIC
        USING(department_id=NULLIF(current_setting('workmate.department_id',true),''))
        WITH CHECK(department_id=NULLIF(current_setting('workmate.department_id',true),''));
  END IF;
END $$;
GRANT SELECT ON workmate_copilot.work_integration_intake TO workmate_scoped_reader;
