# WorkMate AI — Phase 13 controlled pilot and release gate

**Status:** Pilot instrumentation is implemented in GitHub. This document does **not** certify a live warehouse pilot or production readiness. No public staging instance, operator enrollment, actual field observations, final model quality, or human signoffs were performed in CI.

## What the pilot provides

- An opt-in feedback control following a Copilot answer, with only **Helpful** or **Needs review** and one predefined issue category (incorrect guidance, missing evidence, unsafe step, voice transcription or other). The API deliberately accepts **no free-text message or transcript**.
- A manager/admin review page under **Pilot review**, showing only aggregate counts from the signed-in user's own department, never individual employee names, conversation text, voice recordings or SOP passages.
- A PostgreSQL backend recording department, reporter user ID, selected answer area/verdict/issue and created timestamp. User identity is retained **inside the database** for abuse limits/accountability; do not describe it as anonymous raw storage. Department-level reports are de-identified aggregates.
- An explicit cohort flag: `PILOT_FEEDBACK_ENABLED=false` by default. Opting in requires `PILOT_ALLOWED_DEPARTMENTS` to name approved department IDs. No global/implicit department exposure.
- Each reporter has a bounded number of feedback submissions per UTC database day, enforced transactionally; the feedback table has a matching tenant RLS policy. Neither a rating nor a pilot metric advances, pauses or modifies a warehouse workflow.

## Enabling a narrow pilot

Use an already-reviewed HTTPS staging environment with approved, synthetic or independently consented operational data. Provision PostgreSQL migrations with the migration-owner credential, then grant the separate non-owner runtime account using the Phase 11 migration/grant scripts. Confirm that restricted runtime queries without `workmate.department_id` return no feedback or reference rows.

Set only for a pre-agreed pilot cohort:

```text
PILOT_FEEDBACK_ENABLED=true
PILOT_ALLOWED_DEPARTMENTS=receiving-pilot
PILOT_FEEDBACK_MAX_PER_USER_PER_DAY=30
```

Replace `receiving-pilot` with the actual onboarded internal department identifier. This flag enables **feedback collection only**, not authorization for full production rollout or voice model execution. The existing admin/coordinator must provision each user's verified account/department. Do not run CI seed scripts against hosted staging.

Have a trained reviewer inspect each category flagged unsafe and open an independently tracked incident when necessary. This app's aggregate report is a **signal**, not a replacement for incident triage, audit or escalation ownership.

### Retention and privacy

The schema does not store conversation text, question text, recorded audio, IP addresses or free-form operator notes. It **does** store reporter IDs for rate limiting and follows the organization's retention policy. Configure a periodic deletion job or database retention routine before collecting genuine employee feedback; none is automatically scheduled by this PR. Limit operator access to full feedback rows; managers see only department aggregates. Pilot IDs do not authorize cross-department reporting.

## Operator scenarios to verify on real HTTPS staging

1. Admin signs in and imports representative warehouse documents, reviews and approves them, and confirms employees cannot see drafts/archived sources.
2. Employee signs in with HttpOnly Secure cookies, asks reference questions and completes a deterministic **training-only** workflow using explicit human step confirmation.
3. Observe that an answer from a document archived between retrieval and response returns abstention; check citations resolve to current approved reference bytes.
4. Enrolled employee submits a feedback category; manager reviews **department-only** summary. Employee and unenrolled outsider cannot access the aggregate or submit outside the allowlist.
5. Explicitly test mixed Hindi/English transcript review before Send; **do not** treat model speech metrics as proven until the Phase 12 private holdout was evaluated.
6. Disable an employee, reassign department, archive a document, simulate database outage, and verify that the application rejects stale access and fails closed.
7. Test application rollback, off-host encrypted backup and recovery to a separate database; verify source bytes, the current RLS runtime account, and tenant boundaries. Recover using operator-owned backup credentials and offline recovery keys.
8. Collect feedback over the agreed evaluation period. Investigate every unresolved critical finding. A lack of feedback or green synthetic CI alone is not a pass.

## Final go / no-go decision

The source-controlled template at `deploy/pilot/evidence.template.json` contains only **failing** defaults. Copy it to a **private** path, attach third-party evidence outside Git, and update values only after actual human review:

```bash
python scripts/pilot_release_gate.py --evidence /private/pilot-evidence.json --strict
```

The gate requires checked hosted HTTPS, non-owner PostgreSQL runtime, hosted recovery drill, tenant isolation, session revocation, source archiving, voice confirmation, rollback, SOP/security/AI review signoffs; operator days and unique operators; independently annotated English, Hindi and Hinglish question+audio cohorts; zero critical incidents/cross-tenant leaks/invalid citations/unconfirmed autonomous steps; and independently agreed and passed quality thresholds. A missing value means **NO_GO**. It outputs only gate IDs and a SHA-256 of the checklist.

**Limitation:** the checklist is self-attested and cannot independently authenticate signatories, URLs or evidence. A qualified release owner must inspect evidence and approve the decision. Passing the checklist cannot guarantee operational safety.

## Reproducible CI acceptance

- Python unit tests cover feature disabled/default, invalid ratings/issue types, role checks, authenticated scope selection, no raw text, error sanitization, daily limits and release gate failures.
- Real PostgreSQL tests create disposable accounts in two departments, validate manager-only aggregation, daily user limits, and direct RLS tenant isolation under the non-owner staging runtime account.
- Chromium → Next.js → FastAPI → PostgreSQL smoke exercises enrolled employee feedback, unenrolled employee denial, and the manager's actual aggregate UI, in addition to existing document/cookie/CSRF/archival checks.
- CI always asserts that the checked-in release evidence template is **NO_GO**; a synthetic populated checklist may test evaluator logic, but must never be interpreted as a verified field deployment.

## Remaining tasks after code

Hosted staging has not yet been provisioned. Real operator recruitment, consented voice/video, >120 independently labeled QA questions, real-world latency and accuracy, production backup/PITR recovery, broader database RLS and security signoffs remain outstanding. The previous cumulative PR to `main` is still a draft; Phase 13 is stacked on PR #23. Do not merge to main/deploy without a completed independent acceptance gate.
