# Knowledge ingestion production fix

## Root causes

- The API staged uploads before parsing and validation, then returned HTTP 200 even when the compiler reported failure.
- The API advertised PDF, DOCX, and TXT although the implemented compiler accepts only the OWD Markdown DSL.
- Snowflake `PUT` uploaded a random temporary filename while the database stored a different URI, and every upload targeted a shared overwrite-enabled stage path.
- Version 1 was selected whenever the browser omitted `knowledge_item_id`; the browser always omitted it.
- The loader described its work as transactional while relying on Snowflake connector autocommit.
- Compilation invoked Cortex summarization/entity extraction and wrote fabricated embedding/evaluation readiness metadata.
- A legacy n8n callback could mutate the status of a version loaded by the current compiler path.
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

## Deployment prerequisites

- Provision `SNOWFLAKE_STAGE_NAME` ahead of deployment and grant the backend role `WRITE`/`READ` access. Runtime ingestion no longer attempts stage DDL.
- Ensure `SECURITY.departments` contains the active departments shown in the UI.
- Keep the Cortex Search service configured to index `KNOWLEDGE_STUDIO.workflow_search_metadata`; ingestion creates deterministic text search records and does not create vector embeddings.

## Verification

Run:

```bash
PYTHONPATH=.:backend pytest -q backend/tests/test_owd_compiler_subsystem.py backend/tests/test_knowledge_studio.py
npm run build --prefix frontend
```

The ingestion tests cover admin authorization, Markdown-only enforcement, validation-before-staging, server-side version selection, publication success, and removal of the legacy callback.
