-- Direct OWD uploads must pass the same manager approval gate as Procedure Studio drafts.
-- An upload is validated and stored here; it is compiled and published only when a manager
-- approves this exact file. Idempotent.
CREATE TABLE IF NOT EXISTS knowledge_studio.owd_submissions (
  id VARCHAR(64) PRIMARY KEY,
  department_id VARCHAR(64) NOT NULL REFERENCES security.departments(id),
  uploaded_by VARCHAR(64) NOT NULL REFERENCES security.users(id),
  filename VARCHAR(255) NOT NULL,
  title VARCHAR(512) NOT NULL,
  workflow_code VARCHAR(128) NOT NULL,
  version_hint INT NOT NULL CHECK (version_hint >= 1),
  sha256 CHAR(64) NOT NULL,
  content BYTEA NOT NULL,
  status VARCHAR(16) NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','published','returned')),
  decision_note TEXT NULL,
  decided_by VARCHAR(64) NULL REFERENCES security.users(id),
  decided_at TIMESTAMPTZ NULL,
  published_version_id VARCHAR(64) NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CHECK ((status = 'pending' AND decided_by IS NULL) OR (status <> 'pending' AND decided_by IS NOT NULL)),
  CHECK ((status = 'published') = (published_version_id IS NOT NULL))
);
CREATE INDEX IF NOT EXISTS ix_owd_submissions_dept_status
  ON knowledge_studio.owd_submissions (department_id, status, created_at DESC);
-- The same exact bytes cannot be queued twice while pending.
CREATE UNIQUE INDEX IF NOT EXISTS ux_owd_submissions_pending_hash
  ON knowledge_studio.owd_submissions (department_id, sha256) WHERE status = 'pending';
