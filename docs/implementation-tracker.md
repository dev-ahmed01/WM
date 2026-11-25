# WorkMate AI — Implementation Tracker

Branch: `dev/commercial-product` (not pushed; GitHub MCP failed to connect and nothing was pushed). Update at the end of every session.

## Environment (this workstation)
- Windows 11, Python 3.12 venv at `.venv` (3.15 is also installed; do not use), Node 26, Docker Desktop (start it manually; `docker compose up -d postgres`).
- DB: `postgresql://workmate:workmate_dev_only@127.0.0.1:5432/workmate` (compose dev default, local only).
- Backend tests: `PYTHONPATH=backend .venv/Scripts/python -m pytest backend/tests -q` (~7 min). Live DB tests add `WORKMATE_RUN_LIVE_TESTS=1 DATABASE_URL=...`.
- Run backend locally: `APP_ENV=dev DATABASE_URL=... JWT_SECRET=<32+ chars> INTERNAL_WEBHOOK_SECRET=<16+ chars> LOCAL_AI_ENABLED=false VOICE_ENABLED=false PYTHONPATH=backend python -m uvicorn app.main:app --port 8000`
- Demo data: `PYTHONPATH=backend python -m demo.seed_demo` (idempotent; `--republish` recompiles SOPs; `--reset-passwords`). Credentials are written to git-ignored `.demo-credentials.local.json`.
- Assistant eval: `PYTHONPATH=backend python backend/evals/assistant_eval.py --out result.json`.
- Ollama 0.40 on the host has `qwen2.5:3b` and `nomic-embed-text` pulled (2026-11-25). Whisper/Piper/M2M100 models are not downloaded.

## Phase status
| Phase | Status | Evidence |
|---|---|---|
| 1 Audit / baseline / remediation | **Done** | `docs/product-audit.md`; Windows voice-upload 500 fixed |
| 2 Research / personas / PRD | **Done v1 (search-snippet depth only)** | warehouse-research, competitor-analysis, user-personas, product-requirements; gaps listed in each |
| 3 Org / roles / tenant isolation | **Partly done** | Migration 018 (organizations, warehouses, job profiles, user scope, invitation/recovery tokens, cross-org trigger); org-scoped employee admin API; escalations tenant leak fixed; RBAC golden matrix. **Not done:** RLS on workflows/conversations/work tables, manager warehouse scoping in routes, frontend screens for employee management, email delivery of invites (token is shown once to the admin) |
| 4 Knowledge library & approval | **Partly done** | 85 labelled demo SOPs compile through the real OWD compiler; idempotent seeder. **Not done:** approval gate for publishing (upload = publish today), SOP applicability by job profile/warehouse, shared org-wide knowledge scope, versioning policy for in-flight workflows (Scenario I) |
| 5 Assistant quality | **Partly done** | Hindi/Hinglish retrieval fixed, deterministic safety triage, 293-case eval harness. **Not done:** LLM/embedding path untested (no models), citations on catalog path, missing-knowledge escalation (Scenario D), 200-question independent dataset, answer-correctness grading |
| 6 Voice | Not started | needs model downloads for honest benchmarking |
| 7 Actions / escalation loop | Not started | existing work-item/exception infra reused; assistant→action wiring and admin conversation UI missing |
| 8 Admin / manager / analytics | Not started | no employee-management, conversation-management, ROI screens |
| 9 UI polish / accessibility | Not started | frontend untouched this session (typecheck/build pass) |
| 10 Demo / security / deployment | **Started** | seeder + RBAC matrix + live tenant tests. No browser E2E, no deployment benchmark |

## Verified results
- Backend baseline before changes: 358 pass, 15 skip, **1 fail** (Windows voice temp file). After fixes, with live Postgres tests enabled (`WORKMATE_RUN_LIVE_TESTS=1`): **568 passed, 1 skipped, 0 failed**.
- Frontend: `tsc --noEmit` OK; `next build` OK (23 routes).
- Migrations 001–018 apply on fresh PostgreSQL 16.
- New live tests: `test_org_admin_postgres.py` (5) pass — cross-org list/patch/status/recovery denied (404), foreign department/warehouse/supervisor refused, DB trigger rejects cross-org supervisor/warehouse, invite→redeem→login→deactivate→recovery flow, escalation scoping (admin=org, manager=department, orphan invisible).
- `test_demo_sop_catalog.py` (90), `test_safety_triage.py` (21), `test_rbac_matrix.py` (2; 99 operations pinned).
- Live smoke through HTTP: demo picker asks Hinglish/English/Hindi questions; forklift hydraulic-leak report returns stop-work text and creates an urgent escalation visible to the Pune manager.

## Architecture decisions
1. PostgreSQL is the only datastore; Snowflake docs/scripts are obsolete (`seed_test_users.py`, `deploy_owd_schema.py`, `analytics/migrations`, `PROJECT_CONTEXT_V2.md` still describe it — to be removed/marked).
2. Organization sits above departments; departments stay the RLS/knowledge key. A department cannot span organizations (FK + trigger), so department isolation implies organization isolation.
3. **Knowledge scope finding:** retrieval/RLS are per-department, so an employee only sees SOPs of their own department. Demo SOPs therefore live in one department (`dm_ops`) with the functional area as a label. A real multi-department client needs an org-wide "shared" knowledge scope plus job-profile/warehouse applicability filters (Phase 4 follow-up).
4. Safety triage runs before retrieval and any model call and only ever emits fixed stop-work wording; it never gives repair/first-aid steps or claims emergency services were contacted.
5. Role matrix is pinned from observed behaviour (golden file) rather than hand-maintained.
6. Authored retrieval metadata (synonyms/search phrases) is now indexed (`Also known as:`) and used in catalog ranking.

## Defects found and fixed
- Windows: rejected voice upload → 500 (open temp-file handle unlinked).
- `/escalations` list and resolve were not tenant-scoped (any admin/manager saw/resolved every organization's cases).
- Search tokenizer ASCII-only → Devanagari questions returned nothing.
- Compiler never indexed authored synonyms/phrases.
- Seeder idempotency check ignored workflow-code normalization (SOP-X → SOP_X).

## Update after approval to pull models
Done: models pulled; knowledge-gap escalation (Scenario D, first half); live-data guard; truncation fix; full suite 581 pass / 1 skip / 0 fail.
Found: LLM follow-ups take ~10 s on this CPU and hit the 8 s timeout; exception text isn't evidence for the current step.

## Open issues / blockers
- Hindi translation (M2M100) and speech models (Whisper, Piper) still not downloaded/exercised. LLM follow-up latency/timeouts need tuning (see above).
- Out-of-scope questions show unrelated "closest SOP" suggestions and create no escalation.
- Publishing has no approval step; deprecated older version is replaced at upload.
- GitHub MCP not connected; nothing pushed.
- India regulatory content is research-only and needs legal review.

## Next session (recommended order)
1. Missing-knowledge escalation + safe fallback for out-of-scope (Scenario D) and fix truncation bug.
2. Pull models; run eval with LLM/embeddings; measure Hindi/Hinglish; voice benchmark.
3. Publish approval gate + version policy; org-wide knowledge scope; extend RLS.
4. Admin UI: employee management (API exists), conversation/escalation console; manager approvals.
5. Browser E2E (Playwright) for scenarios A–J; screenshots; final report.
