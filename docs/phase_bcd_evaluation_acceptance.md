# WorkMate AI — Evaluation Phases B–D Acceptance

Updated: 2026-10-20. Engineering acceptance is separate from production signoff.

## Implemented Phase B — persistent handovers
Employees explicitly submit a next-shift record linked to a conversation they own. The backend verifies ownership and snapshots its latest recorded workflow position; department and state cannot be selected by an untrusted browser. Managers see a department queue, claim exclusive ownership and acknowledge receipt or request follow-up with a review note. The database records atomic submit, claim and review events, with department-scoped RLS.

## Implemented Phase C — exception triage
Structured exception categories: damaged goods, quantity mismatch, missing document, safety concern and other. Severity normal/high/critical is visible in the manager queue. Critical records require a concrete category; safety concerns cannot be marked information-only. A review acknowledgment NEVER authorizes a safety decision, resolves an exception or advances any workflow. Independent SOP-specific conflict reasoning and automatic escalation delivery remain unclaimed.

## Implemented Phase D — code-level acceptance
- Backend permission, validation and fail-closed tests: backend/tests/test_handover_api.py
- Real PostgreSQL authorization, ownership, tenant RLS and audit acceptance: backend/tests/test_handover_postgres.py
- Real Chromium employee submit → manager claim → follow-up: backend/e2e/browser_smoke.py
- Synthetic browser screenshots uploaded as short-retention CI artifacts by .github/workflows/browser-smoke.yml
- Existing GitHub frontend build, backend regressions, restricted staging checks, and pilot-release gate remain required.
- The checked-in deploy/pilot/evidence.template.json must remain NO_GO without independently approved evidence. Never manufacture a passing field study from synthetic CI.

## Recommended evaluated walkthrough
1. Sign in as an employee, open Operations Desk, and select the receiving/damage starter.
2. Review the editable prompt, send it, and show a real approved SOP or a safe abstention. Advance workflow steps only if the published state permits it.
3. Compare two approved sources in Evidence Explorer. Export the cited evidence.
4. Open Shift Handover for the actual saved session. Choose a realistic exception and severity; supply next action and recipient. Explicitly submit.
5. Switch to a manager account in the same department; open Handover Review, claim ownership, write a reviewer note and request follow-up.
6. Demonstrate that self-review, wrong-department access, duplicate review, and automatic workflow mutation do not occur.
7. Show history, manager analytics and any genuine voice acceptance evidence from the provisioned runtime.

## Acceptance commands
- python scripts/migrate_postgres.py (private dev/isolated database only)
- PYTHONPATH=backend python -m pytest -q backend/tests -m "not live_integration"
- PYTHONPATH=backend WORKMATE_RUN_LIVE_TESTS=1 python -m pytest -q backend/tests/test_handover_postgres.py
- cd frontend && npm ci && npm run typecheck && npm run build

Run the existing browser-smoke workflow against disposable PostgreSQL. Visual inspection needs a desktop view, 375px mobile check, no horizontal overflow, real source citations, visible handover acknowledgment vs issue resolution, keyboard tab navigation and authentication-state correctness. Screenshots MUST show synthetic, non-sensitive content only.

## Known NO-GO gates
External hosted TLS/secure cookie verification, offsite backup and restore drill, non-owner production role confirmation, field Hindi/Hinglish speech testing, independently labeled 120+ question cohort, production model and hardware latency, site-specific SOP review, and signed security/operator release acceptance are not established by a passing CI suite.

Merge order: existing PostgreSQL feature stack, audit PR #25, evaluation PR #26, then this PR #27. Do not merge directly into stale Snowflake main without integration tests and review.
