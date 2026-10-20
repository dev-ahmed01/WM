-- Phase 4B: shift continuity follows the same authenticated task incident and conversation.
-- No migration here authorizes resumption of a blocked task or override of an SOP gate.
ALTER TABLE workmate_copilot.shift_handovers
 ADD COLUMN IF NOT EXISTS work_exception_id VARCHAR(64) NULL
 REFERENCES workmate_copilot.work_exceptions(id);
CREATE UNIQUE INDEX IF NOT EXISTS ux_handover_case_once
 ON workmate_copilot.shift_handovers(work_exception_id)
 WHERE work_exception_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS ix_shift_handover_case
 ON workmate_copilot.shift_handovers(department_id,work_exception_id)
 WHERE work_exception_id IS NOT NULL;

ALTER TABLE workmate_copilot.work_exception_events
 DROP CONSTRAINT IF EXISTS work_exception_events_action_check;
ALTER TABLE workmate_copilot.work_exception_events
 ADD CONSTRAINT work_exception_events_action_check CHECK
 (action IN ('opened','claimed','follow_up_requested','reviewed',
             'containment_recorded','remediation_proposed','handover_linked'));
ALTER TABLE workmate_copilot.work_item_events
 DROP CONSTRAINT IF EXISTS work_item_events_action_check;
ALTER TABLE workmate_copilot.work_item_events
 ADD CONSTRAINT work_item_events_action_check CHECK (
    action IN ('created','assigned','bound','started','step_recorded','decision_recorded',
               'state_advanced','paused','resumed','blocked','completed','exception_claimed',
               'exception_reviewed','exception_follow_up',
               'containment_recorded','remediation_proposed','handover_linked')
 );
