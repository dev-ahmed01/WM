# WorkMate AI — Product Audit (Phase 1)

Audit date: 2026-11-25. Branch: `dev/commercial-product` (from `main` @ `647e71e`, 723 commits).
Method: repository read-through, migration inspection, and baseline execution on Windows 11 / Python 3.12 / Node 26 / Docker Desktop (PostgreSQL 16 container). Where a claim comes from code or a run, it is marked **[verified]**; where it comes from documentation only, **[doc]**.

## 1. Resolved architecture (from executable code, not history)

| Layer | Actual state |
|---|---|
| Database | PostgreSQL 16 only **[verified]**: 17 ordered migrations in `backend/migrations/postgres`, applied by `scripts/migrate_postgres.py`. `PROJECT_CONTEXT_V2.md` still says "Snowflake is the only durable data platform"; this is **obsolete** (README and code say PostgreSQL). |
| Backend | FastAPI, psycopg pool, JWT (python-jose), bcrypt. 15 routers under `backend/app/api/v1` (≈4.7k lines; `copilot.py` alone is 2.2k lines and a refactor candidate). |
| AI | Ollama (chat `qwen2.5:3b`, embeddings `nomic-embed-text` by default), with SQL/extractive fallback. No external model providers. |
| Voice | Faster-Whisper STT, M2M100/CTranslate2 en↔hi translation, Piper TTS, browser speech fallback. |
| Frontend | Next.js 16.3, React 19, Tailwind 3. Route groups `(auth) (employee) (admin) (manager)`. 23 routes. |
| Orchestration | n8n only for optional escalation notifications. |

## 2. Baseline results **[verified]**

| Check | Result |
|---|---|
| `pip install -r backend/requirements.txt` (py3.12) | OK |
| Backend tests (no live DB) | 358 passed, 15 skipped, **1 failed** → fixed (see §4) |
| `npm ci` | OK |
| `tsc --noEmit` | exit 0 |
| `next build` | success, 23 routes |
| PostgreSQL migrations 001–017 on a fresh PG16 | applied cleanly |
| Live-integration tests (`WORKMATE_RUN_LIVE_TESTS=1`) | see tracker for latest result |

The 15 skips are tests that require a live database/services; they are not failures.

## 3. Structural findings

1. **No organisation (company) entity.** Tenancy is a single `security.departments` row; the "tenant" for RLS is `workmate.department_id`. There is no organisation, warehouse, job profile or site table. Multi-company, multi-warehouse and job-profile requirements are therefore **not implemented** (addressed in Phase 3, migration 018).
2. **RLS is partial.** Row-level security is enabled only on `reference_documents`, `reference_chunks`, `source_objects` (migration 003). Workflows, conversations, work items, exceptions, handovers and integration tables rely on application-layer filters.
3. **Dead seeding script.** `backend/scripts/seed_test_users.py` imports `get_snowflake_connection`, which no longer exists. It cannot run. `seed_browser_smoke.py` is the only working seeder and is E2E-only.
4. **Documentation drift.** `PROJECT_CONTEXT_V2.md`, `docs/snowflake_runtime_runbook.md`, `analytics/migrations/*` and `scripts/deploy_owd_schema.py` describe a retired platform.
5. **No demo organisation / SOP library.** The only OWD fixtures are 3 test files for one receiving SOP. There is no 85-SOP library, no demo data seeder, no bilingual evaluation set (only `reference_quality_smoke.json`, `voice_metric_sanity.json`).
6. **Roles** exist (`admin`, `manager`, `employee`) but job profiles, warehouse scope and supervisor relationships do not.

## 4. Defects found and fixed in Phase 1

| Defect | Root cause | Fix |
|---|---|---|
| `test_task_voice_preview_rejects_oversized_audio_before_asr_or_any_write` fails on Windows with `PermissionError [WinError 32]` | `_save_voice_upload` called `unlink` on the temp file while its handle was still open; Windows forbids deleting open files. On Windows this also made every rejected voice upload return HTTP 500 instead of 413/422. | Close the handle before unlinking (`backend/app/api/v1/copilot.py`). |

## 5. Feature-by-feature audit

Status key: **Working** = exercised by passing tests or build; **Partial**; **Missing**.

| Feature | Implementation | Status | Problems / gaps | Proposed action |
|---|---|---|---|---|
| Authentication | `auth.py`, JWT access+refresh, refresh-session revocation, rate-limit windows, bcrypt (migration 003) | Working | No self-service password recovery or invitation flow; no org in token | Add invitations + recovery (Phase 3) |
| RBAC | Role names in `security.roles`; route dependencies; audit middleware | Working (3 roles) | No permission matrix doc/tests per boundary; no job profile; no supervisor scope | Matrix + boundary tests (Phase 3/10) |
| Tenant isolation | Department-scoped queries + RLS on reference tables | Partial | Department ≠ company; RLS limited | Organisation layer + extend RLS (Phase 3) |
| OWD compiler | `backend/app/compiler` parser→validator→compiler→loader; v1.1 spec | Working | Strong; reuse for SOP library | Reuse; generate OWD for SOPs |
| Knowledge Studio (OWD) | `knowledge_studio.py`: upload, publish, version, soft/permanent delete | Working | Org scoping absent; no approval gate for critical changes | Add approval + org (Phase 4) |
| Reference knowledge | Preview extraction (PDF/DOCX/XLSX/PPTX/HTML/CSV/RTF), OCR (Tesseract eng+hin), draft→approve→search with chunks; hybrid retrieval | Working | Markdown/TXT OK; no side-by-side original/extracted viewer verified | Verify UI, extend |
| Procedure Studio | `procedure_drafts` + `procedure_publisher`; draft review UI | Working | Review-to-publish approval roles unclear; no "test before publish" | Add test-ask + manager approval (Phase 4) |
| Copilot | `copilot.py` orchestration, workflow state machine, intent routing, citations, validation | Working | 2.2k-line router; Hinglish/Roman-Hindi coverage unmeasured; no response-mode taxonomy exposed | Evaluation set + targeted fixes (Phase 5) |
| Workflow state | `workflow_state.py`, `workflow_session_repository` | Working | Versioning policy for in-flight sessions not documented | Define + test (Scenario I) |
| Voice | `speech_recognition_*`, `translation_service`, `text_to_speech_service`, browser fallback; voice_quality eval | Working (unit); not exercised with real models in this audit | Heavy model downloads; noisy-audio benchmark absent | Benchmark in Phase 6 |
| Work items / execution | Migrations 006/007, APIs, task guidance panel | Working | Assistant→action wiring limited | Add typed action layer (Phase 7) |
| Exceptions & corrective work | Migrations 010–013 | Working | Employee notification of outcome unverified | Verify (Scenario F) |
| Handover | Migration 005, employee + manager pages | Working | — | Keep |
| Integrations | Signed webhooks, outbox, reconciliation, operator actions (014–017) | Working | Demo vs real connector labelling needed | Label + demo connector |
| Intelligence Hub | `intelligence.py`, analytics events | Working | Metric definitions undocumented; "resolved" semantics unclear; no helpful/not-helpful signal beyond pilot feedback | Define metrics (Phase 8) |
| Pilot gate / feedback | `pilot.py`, `pilot_release_gate.py` | Working | — | Keep |
| Staging deploy | `deploy/staging`, topology + HTTPS checks | Working (tests) | LLM/voice disabled in staging by design | Document VPS+AI profile (Phase 10) |
| Employee management UI | — | **Missing** | No admin employee CRUD/invite screens | Build (Phase 3/8) |
| Conversation management (admin) | Escalations API only | **Missing** | No admin review/assign/respond UI, no FAQ-proposal flow | Build (Phase 7/8) |
| Analytics filters/ROI | — | **Missing** | No warehouse/job-profile filters, no ROI module | Build (Phase 8) |
| Demo environment | — | **Missing** | | Build (Phase 10) |

## 6. Plan implications

Do not rebuild: auth, OWD compiler, reference pipeline, workflow state, work execution, exceptions, integrations, voice stack. Extend: organisation/warehouse/job-profile model, RLS, SOP library & seeding, assistant evaluation, admin/manager screens that are missing.
