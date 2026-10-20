# Phase 3A — source-backed Procedure Studio drafts

## Purpose
Convert an ordinary company document into a **human-reviewed candidate procedure** without granting extracted text the authority of an executable SOP. This replaces the manual first step of transcription and supplies a visual editor and durable version history.

## Work implemented
- `008_procedure_drafts.sql` stores each department's draft, original source reference and digest, extracted step candidates, review status, optimistic revision number, and ordered append-only events. Both draft and event tables use PostgreSQL tenant row-level security.
- Admin-only `/api/v1/procedure/drafts/import` accepts supported office, PDF, textual and selected scanned image files through the existing bounded/private `extract_document` pipeline. It stores the raw file in the existing `shared.source_objects` and creates a source-backed draft in one database transaction.
- The candidate detector only proposes **literal numbered or bullet actions from source text**, capped at 50. It never invents missing actions, approval gates or decision branches.
- Visual editor lets an administrator inspect the first 8,000 characters of extracted source, revise/add/remove instructions, mark each step checked, and save optimistic revisions. An explicit separate review action is blocked until every saved step has been checked.
- Reviewed draft != published workflow. Any edit resets review. The existing compiled OWD publishing authority is unchanged and never called implicitly.
- Browser acceptance tests an actual file upload and saved review. API tests and PostgreSQL live test cover protected access, source checksum/bytes, concurrent revision denial, review refusal and tenant RLS.

## Limits and next Phase 3B
- Imported source may contain warnings from OCR, tables or long document sections. The original binary remains securely stored for provenance. The editor displays a bounded excerpt; a source line number is a reference, not certified accuracy.
- Step candidates are extracted with deterministic text rules; **no claim of AI-written SOPs** is made.
- The compiler still accepts verified OWD Markdown. Bridging reviewed procedure drafts to auto-generated, compiler-validated OWD plus human-supervised publish with decision/evidence editing requires its own tested release.
- A review status alone cannot authorize a safety-sensitive workflow. Hard stops, site-specific rules and regulatory duties require explicit human authoring/approval.
- Audit events are recorded for import, edit and review but this is not an autonomous knowledge publishing agent.

## Release requirements
Run the full quality gates including `test_procedure_drafts_postgres.py`, repeat migration, and test browser SOP import/review against fresh disposable Postgres. Verify no employee can access draft API or UI. Phase 2 evidence gates remain in place. No production authorization until both stacked PRs pass and prior PostgreSQL PR chain is integrated.
