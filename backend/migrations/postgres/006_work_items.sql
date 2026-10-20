-- Phase 1: the operational work item is the product's primary object.
-- This queue does not claim task execution or SOP compliance yet.
CREATE TABLE IF NOT EXISTS workmate_copilot.work_items (
  id VARCHAR(64) PRIMARY KEY,
  department_id VARCHAR(64) NOT NULL REFERENCES security.departments(id),
  created_by VARCHAR(64) NOT NULL REFERENCES security.users(id),
  assigned_to VARCHAR(64) NULL REFERENCES security.users(id),
  external_reference VARCHAR(100) NULL,
  title VARCHAR(180) NOT NULL,
  work_type VARCHAR(24) NOT NULL CHECK
    (work_type IN ('receiving','putaway','stock_count','picking','dispatch','other')),
  priority VARCHAR(16) NOT NULL CHECK (priority IN ('standard','high')),
  instructions VARCHAR(1200) NOT NULL DEFAULT '',
  status VARCHAR(20) NOT NULL DEFAULT 'queued' CHECK (status = 'queued'),
  created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_work_items_department_queue
  ON workmate_copilot.work_items(department_id,created_at DESC);
CREATE INDEX IF NOT EXISTS ix_work_items_assignee
  ON workmate_copilot.work_items(assigned_to,created_at DESC);

CREATE TABLE IF NOT EXISTS workmate_copilot.work_item_events (
  id VARCHAR(64) PRIMARY KEY,
  work_item_id VARCHAR(64) NOT NULL REFERENCES workmate_copilot.work_items(id),
  department_id VARCHAR(64) NOT NULL REFERENCES security.departments(id),
  actor_id VARCHAR(64) NOT NULL REFERENCES security.users(id),
  action VARCHAR(24) NOT NULL CHECK (action = 'created'),
  created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_work_item_events_parent
  ON workmate_copilot.work_item_events(work_item_id,created_at);

ALTER TABLE workmate_copilot.work_items ENABLE ROW LEVEL SECURITY;
ALTER TABLE workmate_copilot.work_item_events ENABLE ROW LEVEL SECURITY;
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies WHERE schemaname='workmate_copilot'
      AND tablename='work_items' AND policyname='wm_work_items_dept'
  ) THEN
    CREATE POLICY wm_work_items_dept ON workmate_copilot.work_items FOR ALL TO PUBLIC
      USING (department_id = NULLIF(current_setting('workmate.department_id',true),''))
      WITH CHECK (department_id = NULLIF(current_setting('workmate.department_id',true),''));
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies WHERE schemaname='workmate_copilot'
      AND tablename='work_item_events' AND policyname='wm_work_events_dept'
  ) THEN
    CREATE POLICY wm_work_events_dept ON workmate_copilot.work_item_events FOR ALL TO PUBLIC
      USING (department_id = NULLIF(current_setting('workmate.department_id',true),''))
      WITH CHECK (department_id = NULLIF(current_setting('workmate.department_id',true),''));
  END IF;
END $$;
GRANT USAGE ON SCHEMA workmate_copilot TO workmate_scoped_reader;
GRANT SELECT ON workmate_copilot.work_items, workmate_copilot.work_item_events TO workmate_scoped_reader;
