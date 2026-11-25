# WorkMate AI — Implementation Tracker

Branch: `dev/commercial-product`. Update this file at the end of every work session.

## Environment (this workstation)
- Windows 11, Python 3.12 venv at `.venv` (3.15 is also installed; use 3.12), Node 26, Docker Desktop (start it manually; `docker compose up -d postgres`).
- DB: `postgresql://workmate:workmate_dev_only@127.0.0.1:5432/workmate` (compose dev default, local only).
- Run backend tests: `PYTHONPATH=backend .venv/Scripts/python -m pytest backend/tests -q` (≈8 min).
- Live DB tests: `WORKMATE_RUN_LIVE_TESTS=1 DATABASE_URL=... pytest ...`.
- Ollama 0.40 installed on host with **no models pulled**; model pulls are large and not yet done.

## Phase status
| Phase | Status | Notes |
|---|---|---|
| 1 Audit/baseline/remediation | **Done** | `docs/product-audit.md`; Windows voice-upload bug fixed |
| 2 Research/personas/PRD | **Done (v1)** | docs/warehouse-research.md, competitor-analysis.md, user-personas.md, product-requirements.md; sources + gaps recorded |
| 3 Org/roles/tenant isolation | Next | migration 018: organizations, warehouses, job_profiles, user scope, RLS |
| 4 Knowledge library & approval | Not started | 85-SOP generator → OWD |
| 5 Assistant quality | Not started | 200-question bilingual eval |
| 6 Voice | Not started | |
| 7 Actions/escalation loop | Not started | |
| 8 Admin/manager/analytics | Not started | |
| 9 UI polish | Not started | |
| 10 Demo/eval/security/deploy | Not started | |

## Verified baseline
- Backend: 358 passed / 15 skipped / 1 failed before fix (fixed; rerun recorded below).
- Frontend: typecheck OK, build OK (23 routes).
- Migrations 001–017 apply on fresh PG16.

## Architecture decisions
1. PostgreSQL is the only datastore; Snowflake docs are obsolete and will be marked/removed.
2. Add an `organizations` layer *above* departments rather than replacing departments: departments become warehouse-scoped units inside an organization. Existing `department_id` columns and RLS GUC stay valid; add `workmate.organization_id` GUC.
3. System role (admin/manager/employee) stays in `security.roles`; job profile, warehouse, supervisor are separate attributes.
4. Reuse OWD compiler for executable SOPs; generate demo SOPs from structured Python data to OWD v1.1 so they pass the real validator.
5. Local Ollama remains the default inference; no external providers.

## Blockers / open items
- No Ollama models installed; model benchmarking, Hindi quality and latency numbers cannot be claimed until pulled (multi-GB download needs user go-ahead on disk/time).
- Whisper/Piper/M2M100 models not downloaded; noisy-audio benchmark pending.
- GitHub MCP failed to connect (auth header); git push/PR not attempted.
- India regulatory mapping is research-only; needs legal review.

## Test log
| Date | Command | Result |
|---|---|---|
| 2026-11-25 | backend pytest -x | 358 pass, 15 skip, 1 fail (voice temp file) |
| 2026-11-25 | tsc / next build | pass |
