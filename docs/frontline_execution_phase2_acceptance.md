# WorkMate — Phase 2 guided execution acceptance

This phase binds each real work item to a department-approved, **published** OWD version and uses the **existing** WORKMATE_COPILOT.workflow_sessions + workflow_step_executions + workflow_evidence_submissions persistence. It does not add a separate arbitrary AI workflow compiler.

## Worker journey
1. Manager creates or assigns work to an active worker within their own department.
2. Manager opens work item, chooses a published SOP version from the same department and links it. Work transitions from queued to ready.
3. Worker opens the item, starts. The service creates a bound workflow session at the first compiled state.
4. The worker sees one pending step at a time and must supply the step's configured confirmation, text observation or numeric reading, plus all required supported evidence.
5. Mandatory PDF and JPEG files are validated for recognizable structure and size (2 MB max each), stored in department-scoped private PostgreSQL objects with SHA-256 fingerprints and recorded as RECEIVED_UNVERIFIED.
6. Atomic PostgreSQL transaction writes the step execution, evidence pointers, workflow state cursor and work event. Replay, stale cursor, missing evidence and simultaneous completion are rejected.
7. Published decision options are selected explicitly; ordinary no-step states may be continued explicitly; pause and resume retain state. A worker can block unsafe work, but cannot release their own blocked task.
8. Manager can review an audit timeline. Work status is not considered completed until the published graph reaches a legitimate terminal state.

## Safety and limits
- No fabricated task counts, source approvals, completion, photo understanding or independent physical verification.
- HARD_STOP, WARNING_CONFIRM, SUPERVISOR_OVERRIDE rules **fail closed** while their trusted evaluation / supervisor-approval route is not yet implemented.
- Unsupported mandatory SIGNATURE, CHECKSUM or SUPERVISOR_APPROVAL evidence specs and configured regex checks are rejected, not silently ignored.
- Revoked or archived published workflow versions stop step progression. Step transition never accepts client-supplied state IDs or arbitrary rule results.
- Legacy Copilot session endpoints and generic session update repository cannot mutate task-bound workflow sessions.
- Blob filenames and bytes are bounded; PDFs/JPEGs must parse structurally. Files do not imply worker actions were verified.
- "Completed" means the worker submitted mandatory evidence/attestations and a published valid branch reached its terminal state, not that a separate auditor certified physical compliance.

## Automated verification
- Unit/API: backend/tests/test_work_execution_api.py and test_work_items_api.py.
- PostgreSQL fixture: backend/tests/test_work_execution_postgres.py — published workflow binding, worker identity isolation, required image, rule gate, branch choice, event ordering, rollback, RLS and status transition replay.
- Browser: backend/e2e/browser_smoke.py — real compiled synthetic SOP and manager binding, worker start, pause/resume, confirmation, JPEG, explicit branch, completed status, legacy-advance bypass denial and wrong-department denial.
- Quality gates: GitHub Actions 10+ real PostgreSQL tests plus backend regression suite, Next.js build and browser acceptance.

## Demo
Use only synthetic warehouse fixture data and the approved, published workflow version. Show supervisor binding → employee step confirmation → demanded photo evidence → correct branch → completed event history. Explain that real WMS information, visual image inspection and independent compliance attestation are future connectors and approval workflows, not features silently enabled in this phase.

## Following phases
3. Procedure Studio document-to-draft workflow editor with human validation.
4. Unified task-linked exception reviews, supervisor approval and event replay.
5. Field-tested multilingual contextual AI (English/Hindi/Hinglish), verified step awareness and refusal testing.
6. Integrations, offline continuity, production secrets/backup drills and operator signoff.

All integration changes remain stacked on prior PostgreSQL PRs. The production gate continues to be NO_GO until externally reviewed evidence is provided.
