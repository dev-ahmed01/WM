# Phase 4D — independently governed case closure

## Decision boundary

A work exception is a separate administrative case, NOT permission to resume its source execution. Phase 4C creates a fresh corrective task; the old work and session stay blocked/paused. Phase 4D adds an auditable *human* closure process:

1. A published corrective SOP is separately approved, executed by its designated employee, and genuinely reaches a terminal state with its required evidence.
2. The **assigned original case reviewer** confirms the completed corrective task, its same-version session and at least one received evidence object, then records a substantive evidence-review note. A stored snapshot references submitted evidence IDs, source SHA-256 hashes, byte sizes, count of recorded steps, and `received_unverified` status. The system never reads a JPEG to infer safety compliance.
3. A **different active departmental administrator**, who was not the reporter, reviewer, proposer, corrective approver, corrective worker, or evidence reviewer, enters the external physical-site inspection record ID, actual observed findings, and explicitly attests to having independently inspected the site. Only then the case changes to `closed`, with immutable timeline actions and two named human signoffs.
4. The **original source work remains `blocked`** and its original SOP session remains `paused`. Closure is an administrative disposition, not resumption or automatic clearance for operating machinery. A new approved assignment is needed for any further work.

## API and controls

`POST /work/exceptions/{case_id}/closure/evidence` — admin/manager, original reviewer only; JSON `expected_revision`, `review_note` (20–1000 chars).

`POST /work/exceptions/{case_id}/closure/site` — admin only, independent named signer also verified against active `security.user_roles`; JSON `expected_revision`, `site_record_reference` (8–128 chars), `site_acceptance_note` (30–1000 chars), and literal `independent_site_inspection_attested:true`. False or absent flag fails validation. Neither API accepts an asserted session ID, evidence ID, department ID, or task status from the browser; facts are retrieved transactionally.

Both endpoints lock the original case/task/session, check actual department and optimistic case revision, enforce prior stages, prevent duplicate decisions, and atomically append named case/work events. Evidence source checksums are rechecked immediately before final signoff. New closure data are governed by department RLS; non-owners only see their department using the established role and row policies.

## Quality gates

- Unit tests: role access, strict payload, explicit true attestation, replay/error redaction.
- Real PostgreSQL integration: blocked source, actual separately approved corrective SOP, worker recording mandatory JPEG, session completion, reviewer checks, independent admin checks, replay/stale revision prevention, cross-department RLS, immutable original hold.
- Browser: complete actual corrective job, independently review, refuse approval from earlier corrective authorizer, accept via separately seeded site admin, verify persisted case `closed` and original task `blocked`.
- Migration 013 double-apply, frontend typecheck/build, browser/CSRF, staging/security checks required on exact final PR HEAD.

## Limits

The database verifies identity, workflow completion, source metadata, evidence integrity and presence of human statements. It **does not independently certify physical site conditions**, employee expertise, or authenticity of external inspection IDs. A controlled CI-site assertion is explicitly synthetic. Real pilots require consenting human operators, on-site inspection and documented external acceptance; current production pilot remains **NO_GO**.
