-- Phase 3B: reviewed draft becomes an explicit compiler-validated published version.
ALTER TABLE knowledge_studio.procedure_drafts
 ADD COLUMN IF NOT EXISTS decision JSONB NOT NULL DEFAULT '{"question":"","options":[]}'::jsonb
 CHECK (jsonb_typeof(decision)='object');
ALTER TABLE knowledge_studio.procedure_drafts
 ADD COLUMN IF NOT EXISTS published_version_id VARCHAR(64) NULL
 REFERENCES knowledge_studio.workflow_versions(id);
ALTER TABLE knowledge_studio.procedure_drafts
 DROP CONSTRAINT IF EXISTS procedure_drafts_status_check;
ALTER TABLE knowledge_studio.procedure_drafts
 ADD CONSTRAINT procedure_drafts_status_check CHECK(status IN ('draft','reviewed','published'));
ALTER TABLE knowledge_studio.procedure_drafts
 ADD CONSTRAINT procedure_drafts_published_state_check CHECK (
   (status='published' AND published_version_id IS NOT NULL)
   OR (status<>'published' AND published_version_id IS NULL)
 );
ALTER TABLE knowledge_studio.procedure_draft_events
 DROP CONSTRAINT IF EXISTS procedure_draft_events_action_check;
ALTER TABLE knowledge_studio.procedure_draft_events
 ADD CONSTRAINT procedure_draft_events_action_check CHECK(
   action IN ('imported','edited','reviewed','published')
 );
CREATE UNIQUE INDEX IF NOT EXISTS ux_procedure_drafts_published_version
 ON knowledge_studio.procedure_drafts(published_version_id)
 WHERE published_version_id IS NOT NULL;
