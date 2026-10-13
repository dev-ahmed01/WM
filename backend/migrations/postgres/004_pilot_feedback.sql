-- Pilot feedback contains deliberately no free text, chat content or audio.
-- Only the signed-in reporter's immutable user/department identity is recorded.
CREATE TABLE IF NOT EXISTS shared.pilot_feedback (
  id VARCHAR(32) PRIMARY KEY,
  department_id VARCHAR(64) NOT NULL REFERENCES security.departments(id),
  reporter_user_id VARCHAR(64) NOT NULL REFERENCES security.users(id),
  surface VARCHAR(16) NOT NULL CHECK (surface IN ('reference','workflow','voice')),
  verdict VARCHAR(16) NOT NULL CHECK (verdict IN ('helpful','needs_review')),
  issue VARCHAR(32) NOT NULL CHECK (issue IN
    ('none','incorrect_guidance','missing_evidence','unsafe_step','voice_transcript','other')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CHECK (
    (verdict='helpful' AND issue='none')
    OR (verdict='needs_review' AND issue <> 'none')
  )
);
CREATE INDEX IF NOT EXISTS ix_pilot_feedback_department_time
  ON shared.pilot_feedback(department_id, created_at DESC);

-- Runtime login must establish transaction-local tenant context.
ALTER TABLE shared.pilot_feedback ENABLE ROW LEVEL SECURITY;
GRANT SELECT ON shared.pilot_feedback TO workmate_scoped_reader;
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies WHERE schemaname='shared'
      AND tablename='pilot_feedback' AND policyname='wm_pilot_department_scope'
  ) THEN
    CREATE POLICY wm_pilot_department_scope ON shared.pilot_feedback
      FOR ALL TO PUBLIC
      USING (department_id = NULLIF(current_setting('workmate.department_id', true), ''))
      WITH CHECK (department_id = NULLIF(current_setting('workmate.department_id', true), ''));
  END IF;
END $$;
