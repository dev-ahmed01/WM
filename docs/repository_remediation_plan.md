# WorkMate AI repository remediation plan

<<<<<<< HEAD
> Historical cleanup plan. Managed Snowflake AI/search was subsequently removed; use `local_ai_runtime.md` and `snowflake_runtime_runbook.md` for current deployment.

=======
>>>>>>> origin/main
## Decision summary

- **Original audited count:** 169 application-repository files; committing this plan made the
  pre-cleanup branch count 170.
- **Implemented target:** 163 tracked files. This removes seven definite generated or
  redundant files without deleting legitimate application modules or tests. The optional
  target is 162 if `Workmate-ai demo.mp4` is moved to a GitHub Release.
- **Do not optimize for the smallest possible number.** The compiler parsers, repositories,
  migrations, tests, package initializers, and AI evaluation are separate architectural
  responsibilities. Removing them to meet an arbitrary count would make the failing paths
  harder to diagnose.
- **Execution model:** one person at a time, in the order below. Each assignment is budgeted
  at about three person-days and ends with a hand-off checkpoint. Person 2 starts only after
  Person 1's branch is merged and deployed to the test environment.

> **Outstanding owner action:** the removed `backend/env-upload.txt` contained live-looking
> Snowflake and application credentials, including a privileged role. Rotate the Snowflake password and
> application secrets now, review access history, and invalidate old credentials. Removing
> the file in a new commit does not remove it from Git history; coordinate history rewriting
> separately after every consumer has moved to the new credentials.

## Person 1 implementation status

Person 1's repository work is complete: the credential file was replaced by a sanitized
`backend/.env.example`; generated reports and TypeScript state were removed and ignored; the
report writer now emits only into `logs/`; stale seed/document snapshots were deleted; repository
instructions and setup documentation were repaired; and automated validation was rerun. Password
and application-secret rotation remains an account-owner operation and was explicitly excluded
from this implementation request.

## Audit findings behind the plan

### Repository hygiene

The seven definite removals are:

1. `frontend/tsconfig.tsbuildinfo` (generated TypeScript build state).
2. `deployment_report.json` and `deployment_report.md` (generated reports).
3. `logs/deployment_report.json` and `logs/deployment_report.md` (duplicate generated reports).
4. `backend/scripts/seed_users_run.py` (stale duplicate of the schema-qualified canonical
   `backend/scripts/seed_test_users.py`).
5. `docs/updated_changes.md` (a stale pasted snapshot of source files).

Rename and sanitize `backend/env-upload.txt` to `backend/.env.example`; that is a net-zero
file-count change and makes the README's setup command truthful. Keep the demo video unless
the owner explicitly chooses release-hosted media. Do not remove `analytics/owd_schema.sql`
until the bootstrap and migration strategies are deliberately unified.

### Why connectivity can pass while upload and Copilot fail

The `/health` database check runs only a simple Snowflake query. It does not prove that the
<<<<<<< HEAD
runtime role can use the warehouse, stage, knowledge tables, local AI provider and semantic index, conversation tables, or escalation tables.
=======
runtime role can use the warehouse, stage, knowledge tables, Cortex Search service, Cortex
model, conversation tables, or escalation tables.
>>>>>>> origin/main

The audited request chain exposes several concrete risks:

1. Upload supports only UTF-8 `.md` files containing the strict OWD workflow format. Ordinary
   Markdown, PDF, and DOCX files are not supported by the current API or UI.
2. Upload performs `PUT` and `LIST` against `RAW_OWD_STAGE`, but no checked-in migration creates
   that stage. A working connection therefore does not imply a working upload.
3. `analytics/migrations/12_runtime_alignment.sql` is absent from the deploy script's migration
   list. The script's comment about migration 11 also contradicts the list that follows it.
4. Retrieval accepts published rows only and applies exact department filtering. An upload
   failure, unrefreshed search service, status mismatch, or JWT department mismatch produces
   no eligible evidence.
<<<<<<< HEAD
5. The historical managed search/generation dependency was removed; local model readiness is now independently observable.
=======
5. The Cortex Search migration has a one-hour target lag and requires separate service and
   Cortex privileges. Model completion has its own role/model availability requirements.
>>>>>>> origin/main
6. Empty retrieval correctly selects the grounded fallback, but fallback handling synchronously
   writes an escalation row. A missing table or DML grant can turn a safe no-evidence response
   into HTTP 500.
7. Runtime configuration loads the ignored `backend/.env`. Deployments must create it from the
   sanitized example or inject the same variables through the hosting platform.

The frontend endpoint paths and multipart upload construction are aligned with the backend.
Start diagnosis at configuration, authorization, schema/stage provisioning, and server-side
error codes rather than renaming frontend endpoints.

## Person 1 — security, file reduction, and code hygiene

**Effort:** approximately three person-days. **Scope:** repository safety and simplification;
do not change ingestion, retrieval, Copilot, or Snowflake runtime behavior.

### 1. Establish the baseline (half day)

1. Read every applicable `AGENTS.md` and the project context.
2. Record `git status --short`, `git ls-files | wc -l`, and the largest tracked files.
3. Run the backend suite from the repository root. Tests currently use root-relative paths, so
   running from `backend/` is not an equivalent baseline.
4. Run a clean frontend install/build. Record existing warnings instead of silently fixing them.

```bash
cd /workspace/WM
find .. -name AGENTS.md -print
git status --short
git ls-files | wc -l
git ls-files -z | xargs -0 du -h | sort -hr | head -30
PYTHONPATH=.:backend python -m pytest -q backend/tests
(cd frontend && npm ci && npm run build)
```

### 2. Resolve the credential incident (half day, separate commit)

1. Confirm the owner has rotated and audited the exposed credentials.
2. Rename `backend/env-upload.txt` to `backend/.env.example`.
3. Replace every account, user, password, JWT secret, webhook secret, and privileged role with
   unmistakable placeholders. Never copy a real credential into an example.
4. Update README environment and startup instructions.
5. Scan the working tree with `git grep` and, when available, gitleaks or trufflehog. Handle Git
   history remediation as an owner-approved operation, not an unannounced force-push.

Checkpoint commit: `security: replace committed credentials with an environment template`.

### 3. Stop tracking generated output (half day, separate commit)

1. Add `*.tsbuildinfo` and the selected deployment-report output directory to `.gitignore`.
2. Change `scripts/load_owd.py` to write reports only to its caller-selected output directory;
   remove its duplicate root-copy behavior.
3. Remove the tracked TypeScript cache and four report snapshots.
4. Run the focused ingestion-script tests and generate a report in a temporary directory. The
   repository must not become dirty.

```bash
git rm frontend/tsconfig.tsbuildinfo \
  deployment_report.json deployment_report.md \
  logs/deployment_report.json logs/deployment_report.md
PYTHONPATH=.:backend python -m pytest -q backend/tests/test_owd_ingestion_pipeline.py
git status --short
```

Checkpoint commit: `chore: stop tracking generated reports and build state`.

### 4. Remove proven redundancy and repair documentation (half day)

1. Remove `backend/scripts/seed_users_run.py`; retain the schema-qualified canonical seed script.
2. Remove `docs/updated_changes.md`; source files and focused design documents remain authoritative.
3. Correct `.agents/AGENTS.md` to reference the repository's actual `PROJECT_CONTEXT_V2.md` via a
   relative link.
4. Add a short repository-tree/ownership section to README rather than another source snapshot.

```bash
rg -n 'seed_users_run|updated_changes|PROJECT_CONTEXT\.md' .
python -m compileall -q backend scripts ai-services
git diff --check
```

Checkpoint commit: `chore: remove stale duplicates and repair repository documentation`.

### 5. Behavior-preserving quality pass and hand-off (one day)

- Search for dead private helpers, TODOs, deprecated APIs, and payload-bearing debug logs. Remove
  code only after reference search and focused tests prove it is unreachable.
- Do not merge compiler parsers, repositories, migrations, or tests solely to reduce file count.
- Decide on one dependency-management policy only if Docker, local setup, and CI consumers are
  updated together.
- Run the complete validation gate and recount. Expected result is **163 tracked files** (or 162
  only with the owner's explicit video decision).

```bash
PYTHONPATH=.:backend python -m pytest -q backend/tests
(cd frontend && npm ci && npm run build)
docker compose config
git diff --check
git ls-files | wc -l
git check-ignore frontend/tsconfig.tsbuildinfo deployment_report.json logs/deployment_report.json
```

**Person 1 acceptance criteria:** no real secrets in the working tree; generated runs leave the
tree clean; one canonical seed command; all documentation links resolve; baseline-passing tests
still pass; tracked count is 163/162. Merge and deploy before Person 2 begins.

## Person 2 — restore upload, ingestion, retrieval, and Copilot

**Effort:** approximately three person-days. **Scope:** runtime functionality and its tests/runbook.
Start from Person 1's merged commit; do not reintroduce reports, credentials, or duplicate scripts.

<<<<<<< HEAD
### Implementation status

Repository-side Person 2 work is complete: core deployment now includes runtime alignment and
stage/side-effect prerequisites; persistence SQL
uses the schemas created by migrations; conversations persist the user's department; and
escalation or analytics failures no longer suppress the canonical fallback. The live deployment,
role grants, upload smoke test, Search refresh, model probe, and two-department matrix remain
environment-owner steps because this repository contains no live credentials. Follow
[`snowflake_runtime_runbook.md`](snowflake_runtime_runbook.md) against the target account.

=======
>>>>>>> origin/main
### 1. Reproduce each boundary independently (quarter day)

Capture the browser request ID, URL, response status, structured `error_code`, and matching backend
log for: login, `GET /knowledge/departments`, upload, and `POST /copilot/message`. Preserve one
failure specimen for each; do not treat all four as a single issue.

### 2. Verify deployed configuration and identity (quarter day)

1. Create a local `backend/.env` from the sanitized example or inject equivalent platform secrets.
2. Confirm frontend API base URL, backend CORS origin, Snowflake account/database/schema/warehouse,
   stage, Search service, and model values in the running deployment—not only in local files.
3. Obtain fresh admin and employee tokens. Decode claims locally and confirm `sub`, token type,
   role, and exact `department_id`; never paste a token into the repository or ticket.

### 3. Make schema deployment complete and repeatable (half day)

1. Compare the deploy script's migration inventory with `analytics/migrations/*.sql`.
2. Add migration 12 in numeric order and resolve the migration-11 comment/list contradiction.
3. Against `INFORMATION_SCHEMA`, verify every knowledge, workflow, conversation, analytics, and
   escalation table/column expected by repositories.
4. Make reruns safe and document the privileged deployment role separately from the runtime role.

### 4. Provision the stage and least-privilege runtime grants (quarter day)

Create `RAW_OWD_STAGE` through an idempotent migration or provisioning script. Grant the backend
role warehouse/database/schema usage, required table DML, and stage read/write. As that exact role,
perform a disposable `PUT`, `LIST`, and cleanup smoke test. A privileged console test is not valid.

### 5. Confirm the ingestion product contract (quarter day)

Choose and document one option before coding:

- **Current MVP:** strict OWD Markdown only. Publish a downloadable canonical template and surface
  parser/validator errors clearly in the UI.
- **Expanded ingestion:** PDF/DOCX/arbitrary Markdown. Treat this as a separate designed pipeline
  with parsing, chunking, metadata, and tests; do not weaken the deterministic OWD validator and
  call that support.

### 6. Prove upload tier by tier (half day)

Test the departments call, an invalid fixture (expected 422), and a canonical valid OWD upload.
For success, assert the staged object exists and the workflow/version is `PUBLISHED`, then check
state, step, and search-metadata counts. Force a loader error once and verify the database
transaction rolls back without claiming publication.

<<<<<<< HEAD
### 7. Prove local semantic retrieval and generation separately (half day)

Verify both Ollama models, index rebuild/refresh, scoped SQL fallback, structured source IDs, and extractive fallback as documented in `local_ai_runtime.md`.
=======
### 7. Prove Cortex Search and completion separately (half day)

1. Deploy the Search-service migration with the required privileged role; grant runtime service
   usage and `SNOWFLAKE.CORTEX_USER` as appropriate for the account.
2. Inspect service status and query it directly with the uploaded document's exact published status
   and department. Account for the one-hour target lag or use an intentionally shorter test lag.
3. Call the configured completion model independently. Distinguish model authorization/region
   failure from retrieval failure, and verify the disabled/unavailable fallback path.
>>>>>>> origin/main

### 8. Make fallback incapable of becoming HTTP 500 (half day)

Qualify escalation/conversation tables with their schemas and isolate nonessential side effects.
The canonical grounded fallback must still return when escalation persistence, analytics, or n8n
is unavailable. Add tests for empty retrieval, missing escalation DML privilege, missing webhook,
valid retrieval, and unavailable completion. Preserve audit visibility rather than swallowing errors.

### 9. End-to-end matrix, observability, and hand-off (half day)

Upload a uniquely worded valid SOP, wait for/index it, authenticate again for fresh claims, and ask
a matching question. Verify answer, citations, confidence, conversation persistence, and workflow
state. Repeat with another department and verify no cross-department evidence leaks. Add a gated
live-Snowflake smoke test and operational runbook. Extend readiness diagnostics to report stage,
schema, Search, and completion capabilities separately from basic connectivity.

```bash
PYTHONPATH=.:backend python -m pytest -q backend/tests
(cd frontend && npm ci && npm run build)
docker compose config
git diff --check
```

**Person 2 acceptance criteria:** a valid OWD upload returns `SUCCESS`/`PUBLISHED` and persisted
counts; a same-department matching query returns a grounded answer with citations and confidence;
empty and cross-department queries return the canonical fallback rather than HTTP 500; Search and
completion capability checks are observable; mocked regression tests plus gated live smoke tests
cover the repaired boundaries.

## Final owner sign-off

The owner should accept the work only after reviewing both PRs, credential rotation evidence,
the 163/162 count, clean full-suite results, and the two-department live matrix. The live matrix is
the proof that Snowflake connectivity, ingestion, indexing, RBAC filtering, completion, validation,
and fallback behavior work together; `/health` alone is not that proof.
