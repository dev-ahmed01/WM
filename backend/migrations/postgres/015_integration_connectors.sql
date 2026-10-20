-- Phase 6B: configured, HMAC-signed connector instances and bounded delivery ledger.
-- No raw source payloads or shared secrets are stored in this ledger.
CREATE TABLE IF NOT EXISTS workmate_copilot.work_integration_sources (
  id VARCHAR(64) PRIMARY KEY,
  department_id VARCHAR(64) NOT NULL REFERENCES security.departments(id),
  source_system VARCHAR(24) NOT NULL CHECK(source_system IN ('sap','oracle','odoo','custom_wms')),
  created_by VARCHAR(64) NOT NULL REFERENCES security.users(id),
  status VARCHAR(12) NOT NULL DEFAULT 'active' CHECK(status IN ('active','disabled')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_wm_connector_dept ON workmate_copilot.work_integration_sources(department_id,status);

CREATE TABLE IF NOT EXISTS workmate_copilot.work_integration_deliveries (
  id VARCHAR(64) PRIMARY KEY,
  department_id VARCHAR(64) NOT NULL REFERENCES security.departments(id),
  source_id VARCHAR(64) NOT NULL REFERENCES workmate_copilot.work_integration_sources(id),
  request_nonce VARCHAR(80) NOT NULL,
  signed_timestamp BIGINT NOT NULL,
  content_sha256 CHAR(64) NOT NULL CHECK(content_sha256 ~ '^[a-f0-9]{64}$'),
  status VARCHAR(12) NOT NULL CHECK(status IN ('staged','replayed','conflict','invalid')),
  reason_code VARCHAR(32) NOT NULL DEFAULT 'none',
  intake_id VARCHAR(64) NULL REFERENCES workmate_copilot.work_integration_intake(id),
  received_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT wm_delivery_nonce_once UNIQUE(source_id,request_nonce)
);
CREATE INDEX IF NOT EXISTS ix_wm_delivery_health ON workmate_copilot.work_integration_deliveries(source_id,received_at DESC);

ALTER TABLE workmate_copilot.work_integration_sources ENABLE ROW LEVEL SECURITY;
ALTER TABLE workmate_copilot.work_integration_deliveries ENABLE ROW LEVEL SECURITY;
DO $$
BEGIN
  IF NOT EXISTS(SELECT 1 FROM pg_policies
    WHERE schemaname='workmate_copilot' AND tablename='work_integration_sources'
      AND policyname='wm_integrations_sources_dept') THEN
    CREATE POLICY wm_integrations_sources_dept ON workmate_copilot.work_integration_sources
      FOR ALL TO PUBLIC USING(department_id=NULLIF(current_setting('workmate.department_id',true),''))
      WITH CHECK(department_id=NULLIF(current_setting('workmate.department_id',true),''));
  END IF;
  IF NOT EXISTS(SELECT 1 FROM pg_policies
    WHERE schemaname='workmate_copilot' AND tablename='work_integration_deliveries'
      AND policyname='wm_integrations_deliveries_dept') THEN
    CREATE POLICY wm_integrations_deliveries_dept ON workmate_copilot.work_integration_deliveries
      FOR ALL TO PUBLIC USING(department_id=NULLIF(current_setting('workmate.department_id',true),''))
      WITH CHECK(department_id=NULLIF(current_setting('workmate.department_id',true),''));
  END IF;
END $$;
GRANT SELECT ON workmate_copilot.work_integration_sources,
  workmate_copilot.work_integration_deliveries TO workmate_scoped_reader;
