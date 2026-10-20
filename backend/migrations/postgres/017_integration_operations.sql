-- Phase 6D: immutable operator response to integration health incidents.
-- Acknowledgements are NOT suppression of live alerts and never modify work.
CREATE TABLE IF NOT EXISTS workmate_copilot.work_integration_operator_actions (
  id VARCHAR(64) PRIMARY KEY,
  department_id VARCHAR(64) NOT NULL REFERENCES security.departments(id),
  source_id VARCHAR(64) NOT NULL REFERENCES workmate_copilot.work_integration_sources(id),
  actor_id VARCHAR(64) NOT NULL REFERENCES security.users(id),
  issue_code VARCHAR(48) NOT NULL CHECK(issue_code IN
    ('dead_outbound','stale_outbound','expired_lease','invalid_inbound',
     'pending_review','signing_key_missing','outbound_unconfigured',
     'connector_disabled','no_recent_receipt')),
  action VARCHAR(24) NOT NULL CHECK(action IN ('acknowledged','remediation_logged')),
  justification VARCHAR(1000) NOT NULL
    CHECK(char_length(trim(justification)) BETWEEN 16 AND 1000),
  created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_wm_operator_actions_source
  ON workmate_copilot.work_integration_operator_actions
    (department_id,source_id,created_at DESC);
ALTER TABLE workmate_copilot.work_integration_operator_actions ENABLE ROW LEVEL SECURITY;
DO $$
BEGIN
  IF NOT EXISTS(SELECT 1 FROM pg_policies
    WHERE schemaname='workmate_copilot' AND tablename='work_integration_operator_actions'
      AND policyname='wm_integration_actions_dept') THEN
    CREATE POLICY wm_integration_actions_dept
      ON workmate_copilot.work_integration_operator_actions FOR ALL TO PUBLIC
      USING(department_id=NULLIF(current_setting('workmate.department_id',true),''))
      WITH CHECK(department_id=NULLIF(current_setting('workmate.department_id',true),''));
  END IF;
END $$;
GRANT SELECT ON workmate_copilot.work_integration_operator_actions
  TO workmate_scoped_reader;
