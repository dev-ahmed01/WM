# WorkMate Frontline Execution — six-phase implementation plan

This is a product repositioning, not a styling patch. The approved architecture retains PostgreSQL, published OWD workflow rules, governed document evidence and identity checks, while replacing a chatbot-centric navigation model.

## Phase 1 — task-first foundation (this PR)
**First-class object:** `workmate_copilot.work_items`, a queued manager-created assignment. The employee sees only assigned work, managers see department work; PostgreSQL tenant RLS prevents accidental cross-department access by restricted DB roles. Each new assignment creates an event, and clients cannot mark execution complete through Phase 1 endpoints.

**New surfaces:**
- My work: priority-filtered queue, real counts, safe empty states, mobile-friendly task tiles.
- Work detail: actual assigned context; a proposed first step must be searched against the *published* SOP via a human-reviewed Copilot draft.
- Control room: supervisor work intake, department queue, pending handover count and follow-up links.
- Procedure Studio: one admin entrance to existing governed workflow publishing and reference approval, no invented PDF-to-workflow automation.
- Navigation: Execute / Knowledge / Supervise, role-specific login landings.

### Phase 1 acceptance criteria
- No fake work items, counts or completion states.
- Employee cannot create tasks or see an unassigned, foreign-owner or foreign-department assignment.
- Manager cannot assign an inactive or cross-department user.
- New work is always queued; no API for bypassing mandatory SOP evidence.
- PostgreSQL migration is repeatable. Audit records and tenant-scoped RLS hold.
- Chromium sees the control room, queues a real assignment, opens it as the right worker and denies outsiders; 375px work desk does not overflow.
- All original voice, reference, auth and knowledge regressions remain green.
- Existing reference and workflow editor routes remain accessible; no migration of customer content is implied.

## Phase 2 — guided work execution
Bind assigned tasks to a *published* workflow version; show one current procedural step at a time. Add typed evidence requirements, barcode/photo inspection adapters, pause/block/escalate, human permission checks, and one append-only event per permitted transition. Provide mandatory evidence and actual current status, not unchecked completion badges. Reuse OWD deterministic rules. Do not write a parallel workflow engine.

## Phase 3 — Procedure Studio creation
Accept ordinary company files into a **draft** workflow builder, extract steps/decisions with confidence flags, require administrator corrections and explicit approval. Publish immutable versions and back-reference page/source offsets. Compare revisions and run deterministic procedure validation before release. Existing governed reference upload and OWD compilation remain in place until replacement parity is proven; do not introduce a second unsynchronized ingestion pipeline.

## Phase 4 — supervisor control and replay
Unify task-level exceptions, attachments, assignees and shift-handovers into one department case timeline. Add reviewer claim, required notes, aging and approved escalation channels. Preserve distinction between review acknowledgment and issue resolution. Support an auditable event replay rather than manufacturing dashboards from sample counts.

## Phase 5 — task-context AI / multilingual
Pass scoped task, verified step, permitted actions and approved SOP version into retrieval. Explicit abstention and escalation for missing/conflicting proof, invalid citations or unsupported actions. Hindi/English/Hinglish microphone flow must require reviewed transcript before consequential messages. No autonomous safety-critical state transition. Independent field WER/CER and error severity evaluation required.

## Phase 6 — integration, quality and pilot
Optional WMS inbound adapters with idempotent ingestion and provenance, mobile offline/resume conflict handling, encrypted evidence retention and purge controls, real consented operator pilots, hosted TLS and backup drills. Release gate remains NO_GO until independent review approves actual latency, security and task-quality targets.

## What Phase 1 deliberately does not claim
No tasks actually execute, no paper SOP is automatically converted, no evidence is independently verified, no external WMS feed is connected, and no AI generated outcome is counted as a completed task. Site-specific SOP and multilingual release signoff remain future gates.

## Run and verify
Use private development PostgreSQL and the repo's existing Compose/CI stack. Apply ordered migrations with `python scripts/migrate_postgres.py`. Run `PYTHONPATH=backend python -m pytest -q backend/tests -m "not live_integration"`; run the full GitHub `quality.yml` including `test_work_items_postgres.py`; use `browser-smoke.yml` for a real Chromium to PostgreSQL check. Frontend: `cd frontend && npm ci && npm run build`.

**Merge order:** prior PostgreSQL feature chain → #25 → #26 → #27 → Phase 1 PR #28. Do not merge this standalone into outdated `main`.
