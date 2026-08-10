# Knowledge ingestion production fix

## Audit summary

| Area | Expected behaviour | Current implementation | Status | Required action |
|---|---|---|---|---|
| Upload boundary | UTF-8 OWD `.md`, 25 MB, validate before staging | Strict BOM-aware UTF-8 decode and parse/validation precede external writes | Verified | None |
| Identity/versioning | Deterministic workflow ID and server-selected version | Parsed workflow code drives UUID and Snowflake version lookup; mismatches return 409 | Verified | Verify concurrent upload policy live |
| Departments | Active Snowflake departments only | Protected list endpoint and active-row validation feed the upload UI | Verified | Seed production departments |
| Staging | Unique safe path, no runtime DDL/overwrite/compression | Sanitized workflow/version/hash path, exact source basename, PUT then LIST | Verified | Provision stage and grants |
| Compiler metadata | Deterministic and honest; no ingestion AI | Deterministic text metadata; embedding/vector not required; evaluation/confidence null | Corrected | Deploy schema-compatible values |
| Loader | Explicit transaction and post-load invariants | BEGIN, all DML, invariant checks, COMMIT/ROLLBACK | Verified | Exercise against target Snowflake |
| Legacy path | Callback/n8n ingestion removed | Callback route absent and 404 covered | Verified | None |
| Upload UI | Database departments and exact success contract | Departments are loaded from API; only SUCCESS/PUBLISHED is shown as success | Corrected | Browser smoke test after deployment |

## Root causes

- The API staged uploads before parsing and validation, then returned HTTP 200 even when the compiler reported failure.
- The API advertised PDF, DOCX, and TXT although the implemented compiler accepts only the OWD Markdown DSL.
- Snowflake `PUT` uploaded a random temporary filename while the database stored a different URI, and every upload targeted a shared overwrite-enabled stage path.
- Version 1 was selected whenever the browser omitted `knowledge_item_id`; the browser always omitted it.
- The loader described its work as transactional while relying on Snowflake connector autocommit.
- Compilation invoked managed summarization/entity extraction and wrote fabricated embedding/evaluation readiness metadata.
- A legacy n8n callback could mutate the status of a version loaded by the current compiler path.
- Dead repository methods from that legacy path could still insert random,
  hard-coded `dept_ops` search rows if called by future code.
- The deployment script could report `SUCCESS` after an in-memory SQLite
  simulation and did not include the managed search migration.
- The upload UI used hard-coded departments that did not match the database.

## Corrected flow

1. Require an admin token and an UTF-8 `.md` file no larger than 25 MB.
2. Parse and validate the OWD source before any external write.
3. Derive the deterministic workflow ID from the parsed workflow code.
4. Validate the selected active department in `SECURITY.departments`.
5. Resolve the next version from Snowflake using the derived workflow ID.
6. Stage the exact source filename at `@<stage>/<workflow-code>/v<version>/<hash-prefix>/...` with compression and overwrite disabled.
7. Compile without AI/network calls.
8. Execute all loader DML inside explicit `BEGIN`/`COMMIT`; roll back on any failure.
9. Verify published status plus expected state and search-record counts before commit.
10. Return success only after the published invariants pass.
11. Deploy all database-only migrations against live Snowflake and return `FAILED` when credentials or connectivity are absent.

## Deployment prerequisites

- Provision `SNOWFLAKE_STAGE_NAME` ahead of deployment and grant the backend role `WRITE`/`READ` access. Runtime ingestion no longer attempts stage DDL.
- Ensure `SECURITY.departments` contains the active departments shown in the UI.
- Ingestion creates deterministic search text only. Runtime local indexing derives disposable embeddings from authorized Snowflake candidates.

## Verification

Run:

```bash
PYTHONPATH=.:backend pytest -q backend/tests/test_owd_compiler_subsystem.py backend/tests/test_knowledge_studio.py
npm run build --prefix frontend
```

The ingestion tests cover admin authorization, Markdown-only enforcement, validation-before-staging, server-side version selection, publication success, and removal of the legacy callback.

## Files changed in this correction set

- `backend/app/api/v1/knowledge_studio.py`
- `backend/app/services/ingestion.py`
- `backend/app/compiler/pipeline.py`
- `backend/app/compiler/compiler.py`
- `backend/app/compiler/models.py`
- `backend/app/compiler/loader.py`
- `backend/app/repositories/knowledge_repository.py`
- `backend/app/models/knowledge.py`
- `frontend/components/upload/UploadDropzone.tsx`
- focused ingestion/compiler/loader tests under `backend/tests/`

## Remaining limitations and live verification

The system intentionally does not ingest PDF, DOCX, TXT, OCR output, or
arbitrary prose. It does not generate embeddings during compilation. Before
production approval, provision `RAW_OWD_STAGE`, grant the backend role stage
READ/WRITE and table DML privileges, seed active departments, upload two
versions of a real OWD, and verify the stage object, deterministic IDs, version
increment, published status, state/search counts, rollback behavior, and local semantic-index refresh in the target account.
