-- Employee-facing simplification: one "case" thread for every request for human help, answer feedback,
-- and conversation titles/archiving for history. Additive only: nothing is dropped or rewritten.

-- 1. Conversation history: employee-editable title and a soft archive (records stay for audit/analytics).
ALTER TABLE workmate_copilot.conversations
  ADD COLUMN IF NOT EXISTS title VARCHAR(160) NULL,
  ADD COLUMN IF NOT EXISTS archived_at TIMESTAMPTZ NULL;
CREATE INDEX IF NOT EXISTS ix_conversation_owner_active
  ON workmate_copilot.conversations (user_id, started_at DESC) WHERE archived_at IS NULL;

-- 2. Helpful / not helpful on an assistant answer. One rating per user per message (re-rating replaces it).
CREATE TABLE IF NOT EXISTS workmate_copilot.message_feedback (
  message_id VARCHAR(64) NOT NULL REFERENCES workmate_copilot.conversation_messages(id),
  user_id VARCHAR(64) NOT NULL REFERENCES security.users(id),
  department_id VARCHAR(64) NOT NULL REFERENCES security.departments(id),
  rating VARCHAR(12) NOT NULL CHECK (rating IN ('helpful','not_helpful')),
  note VARCHAR(500) NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (message_id, user_id)
);
CREATE INDEX IF NOT EXISTS ix_message_feedback_dept ON workmate_copilot.message_feedback (department_id, created_at DESC);

-- 3. Cases: the existing knowledge-gap row becomes the employee's request thread.
ALTER TABLE knowledge_studio.knowledge_gaps
  ADD COLUMN IF NOT EXISTS kind VARCHAR(20) NOT NULL DEFAULT 'unanswered',
  ADD COLUMN IF NOT EXISTS title VARCHAR(200) NULL,
  ADD COLUMN IF NOT EXISTS conversation_id VARCHAR(64) NULL,
  ADD COLUMN IF NOT EXISTS priority VARCHAR(10) NOT NULL DEFAULT 'normal',
  ADD COLUMN IF NOT EXISTS assigned_to VARCHAR(64) NULL REFERENCES security.users(id),
  ADD COLUMN IF NOT EXISTS escalated_to_manager BOOLEAN NOT NULL DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS acknowledged_at TIMESTAMPTZ NULL;
ALTER TABLE knowledge_studio.knowledge_gaps DROP CONSTRAINT IF EXISTS knowledge_gaps_kind_check;
ALTER TABLE knowledge_studio.knowledge_gaps
  ADD CONSTRAINT knowledge_gaps_kind_check CHECK (kind IN ('unanswered','human_request','incorrect_answer'));
ALTER TABLE knowledge_studio.knowledge_gaps DROP CONSTRAINT IF EXISTS knowledge_gaps_priority_check;
ALTER TABLE knowledge_studio.knowledge_gaps
  ADD CONSTRAINT knowledge_gaps_priority_check CHECK (priority IN ('low','normal','high','urgent'));
ALTER TABLE knowledge_studio.knowledge_gaps DROP CONSTRAINT IF EXISTS knowledge_gaps_status_check;
ALTER TABLE knowledge_studio.knowledge_gaps
  ADD CONSTRAINT knowledge_gaps_status_check
  CHECK (status IN ('open','answered','drafting','resolved','dismissed','in_progress','closed'));

-- Only genuinely unanswered questions merge into one counted gap; a request for a person is always its own case.
DROP INDEX IF EXISTS knowledge_studio.ux_knowledge_gaps_live_question;
CREATE UNIQUE INDEX IF NOT EXISTS ux_knowledge_gaps_live_question
  ON knowledge_studio.knowledge_gaps (department_id, lower(question))
  WHERE kind = 'unanswered' AND status IN ('open','answered','drafting','in_progress');
CREATE INDEX IF NOT EXISTS ix_knowledge_gaps_reporter ON knowledge_studio.knowledge_gaps (reported_by, updated_at DESC);
CREATE INDEX IF NOT EXISTS ix_knowledge_gaps_kind ON knowledge_studio.knowledge_gaps (department_id, kind, status);

-- 4. The thread. 'internal' notes are staff-only and never returned to the employee.
CREATE TABLE IF NOT EXISTS knowledge_studio.case_messages (
  id VARCHAR(64) PRIMARY KEY,
  case_id VARCHAR(64) NOT NULL REFERENCES knowledge_studio.knowledge_gaps(id),
  author_id VARCHAR(64) NOT NULL REFERENCES security.users(id),
  author_role VARCHAR(16) NOT NULL CHECK (author_role IN ('employee','manager','admin')),
  kind VARCHAR(12) NOT NULL DEFAULT 'message' CHECK (kind IN ('message','context','event')),
  body TEXT NOT NULL CHECK (length(body) BETWEEN 1 AND 4000),
  internal BOOLEAN NOT NULL DEFAULT FALSE,
  -- clock_timestamp, not CURRENT_TIMESTAMP: messages written in one transaction must keep their order.
  created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
  CHECK (NOT (internal AND author_role = 'employee'))
);
CREATE INDEX IF NOT EXISTS ix_case_messages_case ON knowledge_studio.case_messages (case_id, created_at);
