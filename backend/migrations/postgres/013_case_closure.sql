-- Phase 4D: governed administrative case closure. Physical site truth is an
-- independently recorded human attestation, NOT inferred from photos or AI.
ALTER TABLE workmate_copilot.work_exceptions
  ADD COLUMN IF NOT EXISTS closed_at TIMESTAMPTZ NULL;
ALTER TABLE workmate_copilot.work_exceptions
  DROP CONSTRAINT IF EXISTS work_exceptions_status_check;
ALTER TABLE workmate_copilot.work_exceptions
  ADD CONSTRAINT work_exceptions_status_check
  CHECK (status IN ('open','claimed','follow_up_requested','reviewed','closed'));
ALTER TABLE workmate_copilot.work_exceptions
  DROP CONSTRAINT IF EXISTS work_exception_review_consistency;
ALTER TABLE workmate_copilot.work_exceptions
  ADD CONSTRAINT work_exception_review_consistency CHECK (
    (status IN ('open','claimed') AND reviewed_at IS NULL AND closed_at IS NULL)
    OR (status IN ('follow_up_requested','reviewed') AND reviewed_at IS NOT NULL AND closed_at IS NULL)
    OR (status='closed' AND reviewed_at IS NOT NULL AND closed_at IS NOT NULL)
  );

CREATE TABLE IF NOT EXISTS workmate_copilot.work_case_closures (
  id VARCHAR(64) PRIMARY KEY,
  department_id VARCHAR(64) NOT NULL REFERENCES security.departments(id),
  case_id VARCHAR(64) NOT NULL UNIQUE REFERENCES workmate_copilot.work_exceptions(id),
  corrective_request_id VARCHAR(64) NOT NULL UNIQUE
    REFERENCES workmate_copilot.work_corrective_requests(id),
  corrective_work_id VARCHAR(64) NOT NULL UNIQUE REFERENCES workmate_copilot.work_items(id),
  corrective_session_id VARCHAR(64) NOT NULL REFERENCES workmate_copilot.workflow_sessions(id),
  evidence_snapshot JSONB NOT NULL,
  evidence_reviewed_by VARCHAR(64) NOT NULL REFERENCES security.users(id),
  evidence_review_note VARCHAR(1000) NOT NULL,
  evidence_reviewed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  site_accepted_by VARCHAR(64) NULL REFERENCES security.users(id),
  site_record_reference VARCHAR(128) NULL,
  site_acceptance_note VARCHAR(1000) NULL,
  site_accepted_at TIMESTAMPTZ NULL,
  CONSTRAINT work_case_closure_independence CHECK (
    site_accepted_by IS NULL OR site_accepted_by<>evidence_reviewed_by
  ),
  CONSTRAINT work_case_closure_site_consistency CHECK (
    (site_accepted_by IS NULL AND site_record_reference IS NULL
     AND site_acceptance_note IS NULL AND site_accepted_at IS NULL)
    OR (site_accepted_by IS NOT NULL AND site_record_reference IS NOT NULL
     AND site_acceptance_note IS NOT NULL AND site_accepted_at IS NOT NULL)
  ),
  CONSTRAINT work_case_closure_evidence_object CHECK (jsonb_typeof(evidence_snapshot)='object')
);
CREATE INDEX IF NOT EXISTS ix_case_closures_department
  ON workmate_copilot.work_case_closures(department_id,site_accepted_at);

ALTER TABLE workmate_copilot.work_exception_events
  DROP CONSTRAINT IF EXISTS work_exception_events_action_check;
ALTER TABLE workmate_copilot.work_exception_events
  ADD CONSTRAINT work_exception_events_action_check CHECK (
    action IN ('opened','claimed','follow_up_requested','reviewed',
               'containment_recorded','remediation_proposed','handover_linked',
               'corrective_requested','corrective_approved','corrective_rejected',
               'evidence_reviewed','site_accepted','case_closed')
  );
ALTER TABLE workmate_copilot.work_item_events
  DROP CONSTRAINT IF EXISTS work_item_events_action_check;
ALTER TABLE workmate_copilot.work_item_events
  ADD CONSTRAINT work_item_events_action_check CHECK (
    action IN ('created','assigned','bound','started','step_recorded','decision_recorded',
               'state_advanced','paused','resumed','blocked','completed','exception_claimed',
               'exception_reviewed','exception_follow_up',
               'containment_recorded','remediation_proposed','handover_linked',
               'corrective_requested','corrective_approved','corrective_rejected',
               'evidence_reviewed','site_accepted','case_closed')
  );

ALTER TABLE workmate_copilot.work_case_closures ENABLE ROW LEVEL SECURITY;
DO $$
BEGIN
  IF NOT EXISTS(SELECT 1 FROM pg_policies
    WHERE schemaname='workmate_copilot' AND tablename='work_case_closures'
      AND policyname='wm_case_closures_department') THEN
    CREATE POLICY wm_case_closures_department
      ON workmate_copilot.work_case_closures FOR ALL TO PUBLIC
      USING(department_id=NULLIF(current_setting('workmate.department_id',true),''))
      WITH CHECK(department_id=NULLIF(current_setting('workmate.department_id',true),''));
  END IF;
END $$;
GRANT SELECT ON workmate_copilot.work_case_closures TO workmate_scoped_reader;
