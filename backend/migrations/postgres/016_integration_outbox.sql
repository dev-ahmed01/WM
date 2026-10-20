-- Phase 6C: approved signed source intake -> transactional outbound outbox.
-- Only confirmation of a separately reviewed, QUEUED task is eligible. No
-- work status, SOP session, evidence or safety gate can be changed by a receipt.
CREATE TABLE IF NOT EXISTS workmate_copilot.work_integration_outbox (
  id VARCHAR(64) PRIMARY KEY,
  department_id VARCHAR(64) NOT NULL REFERENCES security.departments(id),
  source_id VARCHAR(64) NOT NULL REFERENCES workmate_copilot.work_integration_sources(id),
  intake_id VARCHAR(64) NOT NULL REFERENCES workmate_copilot.work_integration_intake(id),
  work_item_id VARCHAR(64) NOT NULL REFERENCES workmate_copilot.work_items(id),
  event_type VARCHAR(32) NOT NULL DEFAULT 'work_accepted'
    CHECK(event_type='work_accepted'),
  payload JSONB NOT NULL CHECK(jsonb_typeof(payload)='object'),
  status VARCHAR(16) NOT NULL DEFAULT 'pending'
    CHECK(status IN ('pending','leased','delivered','dead')),
  attempts SMALLINT NOT NULL DEFAULT 0 CHECK(attempts BETWEEN 0 AND 5),
  next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  lease_token VARCHAR(64),
  lease_expires_at TIMESTAMPTZ,
  ack_reference VARCHAR(100),
  last_error_code VARCHAR(48),
  recovered_count SMALLINT NOT NULL DEFAULT 0 CHECK(recovered_count BETWEEN 0 AND 3),
  created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  delivered_at TIMESTAMPTZ,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT wm_outbox_one_event UNIQUE(intake_id,event_type),
  CONSTRAINT wm_outbox_lease_consistency CHECK(
    (status='leased' AND lease_token IS NOT NULL AND lease_expires_at IS NOT NULL)
    OR (status<>'leased' AND lease_token IS NULL AND lease_expires_at IS NULL)
  ),
  CONSTRAINT wm_outbox_ack_consistency CHECK(
    (status='delivered' AND ack_reference IS NOT NULL AND delivered_at IS NOT NULL)
    OR (status<>'delivered' AND ack_reference IS NULL AND delivered_at IS NULL)
  )
);
CREATE INDEX IF NOT EXISTS ix_wm_outbox_claim ON workmate_copilot.work_integration_outbox(status,next_attempt_at,created_at);
CREATE INDEX IF NOT EXISTS ix_wm_outbox_source ON workmate_copilot.work_integration_outbox(department_id,source_id,status);

CREATE TABLE IF NOT EXISTS workmate_copilot.work_integration_outbox_attempts (
  id VARCHAR(64) PRIMARY KEY,
  department_id VARCHAR(64) NOT NULL REFERENCES security.departments(id),
  outbox_id VARCHAR(64) NOT NULL REFERENCES workmate_copilot.work_integration_outbox(id),
  attempt_number SMALLINT NOT NULL,
  result VARCHAR(16) NOT NULL CHECK(result IN ('delivered','retry','dead')),
  code VARCHAR(48) NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_wm_outbox_attempts ON workmate_copilot.work_integration_outbox_attempts(outbox_id,created_at);

CREATE TABLE IF NOT EXISTS workmate_copilot.work_integration_outbox_recoveries (
  id VARCHAR(64) PRIMARY KEY,
  department_id VARCHAR(64) NOT NULL REFERENCES security.departments(id),
  outbox_id VARCHAR(64) NOT NULL REFERENCES workmate_copilot.work_integration_outbox(id),
  actor_id VARCHAR(64) NOT NULL REFERENCES security.users(id),
  justification VARCHAR(1000) NOT NULL CHECK(length(trim(justification))>=16),
  created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_wm_outbox_recoveries ON workmate_copilot.work_integration_outbox_recoveries(outbox_id,created_at);
ALTER TABLE workmate_copilot.work_integration_outbox ENABLE ROW LEVEL SECURITY;
ALTER TABLE workmate_copilot.work_integration_outbox_attempts ENABLE ROW LEVEL SECURITY;
ALTER TABLE workmate_copilot.work_integration_outbox_recoveries ENABLE ROW LEVEL SECURITY;
DO $$
DECLARE t TEXT;
BEGIN
  FOREACH t IN ARRAY ARRAY['work_integration_outbox','work_integration_outbox_attempts','work_integration_outbox_recoveries']
  LOOP
    IF NOT EXISTS (SELECT 1 FROM pg_policies
      WHERE schemaname='workmate_copilot' AND tablename=t AND policyname='wm_outbox_department') THEN
      EXECUTE format('CREATE POLICY wm_outbox_department ON workmate_copilot.%I
        FOR ALL TO PUBLIC
        USING (department_id=NULLIF(current_setting(''workmate.department_id'',true),''''))
        WITH CHECK (department_id=NULLIF(current_setting(''workmate.department_id'',true),''''))',t);
    END IF;
  END LOOP;
END $$;
GRANT SELECT ON workmate_copilot.work_integration_outbox,
  workmate_copilot.work_integration_outbox_attempts,
  workmate_copilot.work_integration_outbox_recoveries TO workmate_scoped_reader;
