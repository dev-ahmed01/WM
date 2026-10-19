-- Evaluation Phase B/C: persisted handovers and review, separated from SOP execution.
-- Review means acknowledgment, NEVER verification of the work or safety approval.
CREATE TABLE IF NOT EXISTS workmate_copilot.shift_handovers (
    id VARCHAR(64) PRIMARY KEY,
    department_id VARCHAR(64) NOT NULL REFERENCES security.departments(id),
    conversation_id VARCHAR(64) NOT NULL REFERENCES workmate_copilot.conversations(id),
    created_by VARCHAR(64) NOT NULL REFERENCES security.users(id),
    recipient_label VARCHAR(100) NOT NULL,
    disposition VARCHAR(32) NOT NULL CHECK (disposition IN
      ('pending_next_shift','blocked_supervisor','information','follow_up')),
    exception_type VARCHAR(32) NOT NULL DEFAULT 'none' CHECK (exception_type IN
      ('none','damage','quantity_mismatch','missing_document','safety_concern','other')),
    severity VARCHAR(16) NOT NULL DEFAULT 'normal' CHECK (severity IN ('normal','high','critical')),
    next_action VARCHAR(1500) NOT NULL,
    notes VARCHAR(1500) NOT NULL DEFAULT '',
    snapshot_state JSONB NOT NULL DEFAULT '{}'::jsonb,
    status VARCHAR(32) NOT NULL DEFAULT 'submitted' CHECK (status IN
      ('submitted','acknowledged','follow_up_requested')),
    reviewed_by VARCHAR(64) NULL REFERENCES security.users(id),
    reviewed_at TIMESTAMPTZ NULL,
    review_note VARCHAR(1000) NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT handover_critical_exception CHECK (
      severity <> 'critical' OR exception_type <> 'none'),
    CONSTRAINT handover_review_coherent CHECK (
      (status = 'submitted' AND reviewed_by IS NULL AND reviewed_at IS NULL)
      OR (status <> 'submitted' AND reviewed_by IS NOT NULL AND reviewed_at IS NOT NULL))
);
CREATE INDEX IF NOT EXISTS ix_handover_department_status
    ON workmate_copilot.shift_handovers (department_id,status,created_at DESC);
CREATE INDEX IF NOT EXISTS ix_handover_owner
    ON workmate_copilot.shift_handovers (created_by,created_at DESC);

CREATE TABLE IF NOT EXISTS workmate_copilot.shift_handover_events (
    id VARCHAR(64) PRIMARY KEY,
    handover_id VARCHAR(64) NOT NULL REFERENCES workmate_copilot.shift_handovers(id) ON DELETE CASCADE,
    department_id VARCHAR(64) NOT NULL REFERENCES security.departments(id),
    actor_user_id VARCHAR(64) NOT NULL REFERENCES security.users(id),
    action VARCHAR(32) NOT NULL CHECK (action IN ('submitted','acknowledged','follow_up_requested')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_handover_events_handover
    ON workmate_copilot.shift_handover_events (handover_id,created_at);

-- The app scopes every query AND the non-owner staging runtime is protected by RLS.
ALTER TABLE workmate_copilot.shift_handovers ENABLE ROW LEVEL SECURITY;
ALTER TABLE workmate_copilot.shift_handover_events ENABLE ROW LEVEL SECURITY;
DO $$
BEGIN
 IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname='workmate_copilot'
    AND tablename='shift_handovers' AND policyname='wm_handover_scope') THEN
   CREATE POLICY wm_handover_scope ON workmate_copilot.shift_handovers
   FOR ALL TO PUBLIC
   USING (department_id = NULLIF(current_setting('workmate.department_id',true),''))
   WITH CHECK (department_id = NULLIF(current_setting('workmate.department_id',true),''));
 END IF;
 IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname='workmate_copilot'
    AND tablename='shift_handover_events' AND policyname='wm_handover_event_scope') THEN
   CREATE POLICY wm_handover_event_scope ON workmate_copilot.shift_handover_events
   FOR ALL TO PUBLIC
   USING (department_id = NULLIF(current_setting('workmate.department_id',true),''))
   WITH CHECK (department_id = NULLIF(current_setting('workmate.department_id',true),''));
 END IF;
END $$;
