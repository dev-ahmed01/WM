-- Phase 10: explicitly scoped reference reader and durable session/abuse controls.
-- Runtime app login must be GRANTed membership in workmate_scoped_reader by the
-- database operator; application credentials must not own protected tables.
CREATE TABLE IF NOT EXISTS security.refresh_sessions (
  jti_hash VARCHAR(64) PRIMARY KEY,
  user_id VARCHAR(64) NOT NULL REFERENCES security.users(id),
  issued_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  expires_at TIMESTAMPTZ NOT NULL,
  revoked_at TIMESTAMPTZ,
  rotated_to_hash VARCHAR(64)
);
CREATE INDEX IF NOT EXISTS ix_refresh_sessions_user_active
  ON security.refresh_sessions (user_id, expires_at) WHERE revoked_at IS NULL;

CREATE TABLE IF NOT EXISTS security.auth_rate_windows (
  key_hash VARCHAR(64) NOT NULL,
  action VARCHAR(32) NOT NULL,
  window_started TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  attempts INTEGER NOT NULL DEFAULT 1 CHECK (attempts >= 0),
  PRIMARY KEY (key_hash, action)
);

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'workmate_scoped_reader') THEN
    CREATE ROLE workmate_scoped_reader NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION;
  END IF;
END $$;

GRANT USAGE ON SCHEMA knowledge_studio, shared TO workmate_scoped_reader;
GRANT SELECT ON knowledge_studio.reference_documents,
                knowledge_studio.reference_chunks,
                shared.source_objects TO workmate_scoped_reader;

-- Policies are role-targeted: they never authorize unscoped application reads.
-- A missing tenant config resolves to NULL and yields zero rows.
ALTER TABLE knowledge_studio.reference_documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE knowledge_studio.reference_chunks ENABLE ROW LEVEL SECURITY;
ALTER TABLE shared.source_objects ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname='knowledge_studio'
                    AND tablename='reference_documents' AND policyname='wm_reference_read_scope') THEN
    CREATE POLICY wm_reference_read_scope
      ON knowledge_studio.reference_documents FOR SELECT TO workmate_scoped_reader
      USING (department_id = NULLIF(current_setting('workmate.department_id', true), ''));
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname='knowledge_studio'
                    AND tablename='reference_chunks' AND policyname='wm_chunk_read_scope') THEN
    CREATE POLICY wm_chunk_read_scope
      ON knowledge_studio.reference_chunks FOR SELECT TO workmate_scoped_reader
      USING (department_id = NULLIF(current_setting('workmate.department_id', true), ''));
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname='shared'
                    AND tablename='source_objects' AND policyname='wm_source_read_scope') THEN
    CREATE POLICY wm_source_read_scope
      ON shared.source_objects FOR SELECT TO workmate_scoped_reader
      USING (department_id = NULLIF(current_setting('workmate.department_id', true), ''));
  END IF;
END $$;

-- Grant role membership to the bootstrap schema owner for CI and migrations.
-- Production runtime login MUST be explicitly granted by the DB operator.
DO $$
BEGIN
  EXECUTE format('GRANT workmate_scoped_reader TO %I', current_user);
END $$;
