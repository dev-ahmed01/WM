-- Closed knowledge loop: unanswered question -> gap record -> supervisor reply ->
-- proposed SOP draft -> manager approval -> publish. A reply never becomes
-- authoritative knowledge; only an approved, published SOP does.

CREATE TABLE IF NOT EXISTS knowledge_studio.knowledge_gaps (
  id VARCHAR(64) PRIMARY KEY,
  department_id VARCHAR(64) NOT NULL REFERENCES security.departments(id),
  reported_by VARCHAR(64) NOT NULL REFERENCES security.users(id),
  conversation_message_id VARCHAR(64) NULL,
  escalation_id VARCHAR(64) NULL,
  question TEXT NOT NULL CHECK (length(question) BETWEEN 3 AND 1000),
  occurrences INT NOT NULL DEFAULT 1 CHECK (occurrences >= 1),
  status VARCHAR(16) NOT NULL DEFAULT 'open'
    CHECK (status IN ('open','answered','drafting','resolved','dismissed')),
  employee_reply TEXT NULL CHECK (employee_reply IS NULL OR length(employee_reply) BETWEEN 3 AND 1500),
  replied_by VARCHAR(64) NULL REFERENCES security.users(id),
  replied_at TIMESTAMPTZ NULL,
  draft_id VARCHAR(64) NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  resolved_at TIMESTAMPTZ NULL
);
-- One live gap per distinct question per department; repeats increment occurrences.
CREATE UNIQUE INDEX IF NOT EXISTS ux_knowledge_gaps_live_question
  ON knowledge_studio.knowledge_gaps (department_id, lower(question))
  WHERE status IN ('open','answered','drafting');
CREATE INDEX IF NOT EXISTS ix_knowledge_gaps_dept_status
  ON knowledge_studio.knowledge_gaps (department_id, status, updated_at DESC);

-- No RLS here on purpose: admins read across departments of their organization, which a single
-- department GUC policy cannot express. Access is scoped in the repository by organization/department.

-- Manager approval of a reviewed draft revision (editing bumps revision, which voids it).
ALTER TABLE knowledge_studio.procedure_drafts
  ADD COLUMN IF NOT EXISTS approved_by VARCHAR(64) NULL REFERENCES security.users(id),
  ADD COLUMN IF NOT EXISTS approved_at TIMESTAMPTZ NULL,
  ADD COLUMN IF NOT EXISTS approved_revision INT NULL,
  ADD COLUMN IF NOT EXISTS rejection_note TEXT NULL,
  ADD COLUMN IF NOT EXISTS source_gap_id VARCHAR(64) NULL;

ALTER TABLE knowledge_studio.procedure_draft_events
  DROP CONSTRAINT IF EXISTS procedure_draft_events_action_check;
ALTER TABLE knowledge_studio.procedure_draft_events
  ADD CONSTRAINT procedure_draft_events_action_check
  CHECK (action IN ('imported','edited','reviewed','approved','returned','published'));
