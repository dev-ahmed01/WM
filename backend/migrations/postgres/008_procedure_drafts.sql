-- Phase 3A: reviewable source-to-procedure drafts. No automatic publication.
CREATE TABLE IF NOT EXISTS knowledge_studio.procedure_drafts (
  id VARCHAR(64) PRIMARY KEY,
  department_id VARCHAR(64) NOT NULL REFERENCES security.departments(id),
  created_by VARCHAR(64) NOT NULL REFERENCES security.users(id),
  source_object_id VARCHAR(32) NOT NULL REFERENCES shared.source_objects(id),
  source_sha256 VARCHAR(64) NOT NULL,
  source_filename VARCHAR(255) NOT NULL,
  source_type VARCHAR(16) NOT NULL,
  title VARCHAR(180) NOT NULL,
  source_excerpt TEXT NOT NULL,
  steps JSONB NOT NULL DEFAULT '[]'::jsonb
    CHECK (jsonb_typeof(steps)='array'),
  warnings JSONB NOT NULL DEFAULT '[]'::jsonb
    CHECK (jsonb_typeof(warnings)='array'),
  status VARCHAR(16) NOT NULL DEFAULT 'draft'
    CHECK (status IN ('draft','reviewed')),
  revision INT NOT NULL DEFAULT 1 CHECK (revision BETWEEN 1 AND 100000),
  reviewed_by VARCHAR(64) NULL REFERENCES security.users(id),
  reviewed_at TIMESTAMPTZ NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_procedure_drafts_department
  ON knowledge_studio.procedure_drafts(department_id,updated_at DESC);
CREATE TABLE IF NOT EXISTS knowledge_studio.procedure_draft_events (
  seq BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  draft_id VARCHAR(64) NOT NULL REFERENCES knowledge_studio.procedure_drafts(id),
  department_id VARCHAR(64) NOT NULL REFERENCES security.departments(id),
  actor_id VARCHAR(64) NOT NULL REFERENCES security.users(id),
  action VARCHAR(16) NOT NULL CHECK(action IN ('imported','edited','reviewed')),
  revision INT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
ALTER TABLE knowledge_studio.procedure_drafts ENABLE ROW LEVEL SECURITY;
ALTER TABLE knowledge_studio.procedure_draft_events ENABLE ROW LEVEL SECURITY;
DO $$
BEGIN
  IF NOT EXISTS(SELECT 1 FROM pg_policies WHERE schemaname='knowledge_studio'
    AND tablename='procedure_drafts' AND policyname='procedure_drafts_department') THEN
    CREATE POLICY procedure_drafts_department ON knowledge_studio.procedure_drafts
      USING (department_id=NULLIF(current_setting('workmate.department_id',true),''))
      WITH CHECK (department_id=NULLIF(current_setting('workmate.department_id',true),''));
  END IF;
  IF NOT EXISTS(SELECT 1 FROM pg_policies WHERE schemaname='knowledge_studio'
    AND tablename='procedure_draft_events' AND policyname='procedure_draft_events_department') THEN
    CREATE POLICY procedure_draft_events_department ON knowledge_studio.procedure_draft_events
      USING (department_id=NULLIF(current_setting('workmate.department_id',true),''))
      WITH CHECK (department_id=NULLIF(current_setting('workmate.department_id',true),''));
  END IF;
END $$;
GRANT USAGE ON SCHEMA knowledge_studio TO workmate_scoped_reader;
GRANT SELECT ON knowledge_studio.procedure_drafts,knowledge_studio.procedure_draft_events
  TO workmate_scoped_reader;
