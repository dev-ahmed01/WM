# WorkMate integration audit — cumulative release into main (2026-10-20)

## Scope / ancestry

Integration base: `main` @ `ea7cc66ca0d536e71cdbc041e726672102f337ec`.
Verified cumulative implementation: Phase 6D @ `b6e9796891cab7564b36027927aea1fbc007dd0b`.

The repository has 31 open Phase 1–6D PRs (#11–#41), most arranged as a dependency stack. PR #20 duplicates the Phase 1–9 series (#11–#19) as a cumulative draft. A single consolidated integration PR into main is preferred over squashing the staged PRs individually out of sequence; that would discard exact tested ancestry, duplicate commit histories, and make dependencies difficult to reason about.

`main` diverged from the stack with exactly two legitimate pilot-security commits (tenant RLS and transaction-local scope). The integration reconciles those changes deliberately: **retain the exact current main `backend/app/repositories/pilot_repository.py`**, because it already enforces transaction-local tenant identity, and retain the feature tree's `backend/migrations/postgres/004_pilot_feedback.sql`, because it preserves the same RLS policy and adds required scoped-reader GRANT. Both main commits are retained as a **merge parent**, not overwritten in Git history.

## Safety and release conditions

- Full integration CI must pass **against the final merge-resolution tree**: document/backend tests, PostgreSQL migration replay and restore, live tenant/RLS security, actual Chromium browser workflow, frontend typecheck/build, and staging-role security.
- Confirm `deploy/pilot/evidence.template.json` fails closed with `NO_GO`, including actual audio QA, partner security gates, real ingress TLS, egress blocking and deployment/rollback evidence.
- No production deployment workflows exist in `.github/workflows` in this source tree; existing workflows perform quality, Chromium smoke and staging preflight checks only. Merging code into main is **not** field deployment.
- Operator must separately configure real Kubernetes/VPS/Compose targets and secret manager, hosted HTTPS/mTLS/egress constraints, and follow independent acceptance before attempting a production pilot. This is not authorization to enable signed webhooks or outbound workers.
- Keep an actual partner endpoint and its credentials disconnected; outbound `WORKMATE_OUTBOUND_ENABLED` remains default false.
- Real pilot release stays `NO_GO`; `main` code-integrated is not product-launched.

## Verification and rollback

The consolidated PR's HEAD is the only authoritative branch for acceptance. Only after every exact-HEAD GitHub Action run succeeds should the integration PR be merged into main with the expected HEAD SHA. Keep the merge commit and parent SHAs as immutable rollback anchors. If post-merge workflow fails, stop any promotion, revert the merge via reviewed PR, and rerun restore and RLS checks. Do not force push main or delete historical work until lineage and CI references are preserved.

Prior work: staged Phases 1–9, production security/staging/pilot, evaluation operations, Frontline Execution Phases 1–5, independent incident closure 4D, and signed integration Phases 6A–6D. All remain subject to actual live source and warehouse field validation.
