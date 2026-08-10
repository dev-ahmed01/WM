<<<<<<< HEAD
# Snowflake database/stage and local AI runtime runbook

Snowflake is used only for relational persistence, OWD source staging, and authorized retrieval
candidate reads. All AI runs through local Ollama.

## 1. Configure locally

```bash
cp backend/.env.example backend/.env
# Replace sanitized placeholders only in ignored backend/.env.
```

Use a least-privilege runtime role, `COPILOT_ALLOWED_KNOWLEDGE_STATUSES=published`, and the Compose
Ollama hostname shown in the template.

## 2. Deploy database objects

```bash
PYTHONPATH=.:backend python scripts/deploy_owd_schema.py
```

The deployment contains schemas, normalized OWD tables, security, conversations, analytics,
runtime alignment, and `RAW_OWD_STAGE`. There is no managed AI migration or grant.

Apply account-specific runtime grants for warehouse/database/schema usage, required table DML, and
stage read/write. Do not give the FastAPI user object-owner or account-administration roles.

## 3. Verify as the backend role
=======
# Snowflake ingestion and Copilot runtime runbook

This runbook separates basic connectivity from the capabilities required by knowledge upload and
Copilot. Run deployment commands with an object-owning role. Run every smoke check a second time
with the least-privilege backend role configured in `backend/.env`.

## 1. Deploy core objects

```bash
cp backend/.env.example backend/.env
# Fill backend/.env locally; never commit it.
PYTHONPATH=.:backend python scripts/deploy_owd_schema.py
```

The core deployment includes department alignment, `RAW_OWD_STAGE`, conversation/escalation
alignment, and generic Copilot telemetry. It deliberately excludes Cortex Search because service
creation commonly needs a more privileged role.

## 2. Deploy Cortex Search

Set `SNOWFLAKE_ROLE` to the approved Cortex deployment role, then run:

```bash
PYTHONPATH=.:backend python scripts/deploy_owd_schema.py --include-cortex
```

The command reruns idempotent core DDL and creates the Search service in numeric migration order.
Grant the backend role the account-specific equivalent of:

```sql
GRANT DATABASE ROLE SNOWFLAKE.CORTEX_USER TO ROLE WORKMATE_BACKEND_ROLE;
GRANT USAGE ON CORTEX SEARCH SERVICE
  WORKMATE_AI.KNOWLEDGE_STUDIO.WORKMATE_KNOWLEDGE_SEARCH
  TO ROLE WORKMATE_BACKEND_ROLE;
```

## 3. Apply least-privilege runtime grants

Replace `WORKMATE_BACKEND_ROLE` before executing these statements:

```sql
GRANT USAGE ON WAREHOUSE COMPUTE_WH TO ROLE WORKMATE_BACKEND_ROLE;
GRANT USAGE ON DATABASE WORKMATE_AI TO ROLE WORKMATE_BACKEND_ROLE;
GRANT USAGE ON ALL SCHEMAS IN DATABASE WORKMATE_AI TO ROLE WORKMATE_BACKEND_ROLE;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN DATABASE WORKMATE_AI
  TO ROLE WORKMATE_BACKEND_ROLE;
GRANT READ, WRITE ON STAGE WORKMATE_AI.KNOWLEDGE_STUDIO.RAW_OWD_STAGE
  TO ROLE WORKMATE_BACKEND_ROLE;
```

Use managed future grants when appropriate for the account. Do not give the FastAPI runtime an
owner or account-administration role.

## 4. Verify objects as the backend role
>>>>>>> origin/main

```sql
SELECT CURRENT_ROLE(), CURRENT_DATABASE(), CURRENT_SCHEMA(), CURRENT_WAREHOUSE();
LIST @WORKMATE_AI.KNOWLEDGE_STUDIO.RAW_OWD_STAGE;
SELECT COUNT(*) FROM WORKMATE_AI.SECURITY.departments WHERE is_active = TRUE;
SELECT COUNT(*) FROM WORKMATE_AI.KNOWLEDGE_STUDIO.workflow_search_metadata;
SELECT COUNT(*) FROM WORKMATE_AI.WORKMATE_COPILOT.conversations;
SELECT COUNT(*) FROM WORKMATE_AI.WORKMATE_COPILOT.escalation_records;
SELECT COUNT(*) FROM WORKMATE_AI.INTELLIGENCE_HUB.analytics_events;
<<<<<<< HEAD
```

A basic `/health` result does not prove stage or table privileges. Perform a disposable `PUT`,
`LIST`, and `REMOVE` with the actual backend role.

## 4. Start and verify Ollama

```bash
docker compose up --build
curl --fail http://localhost:11434/api/tags
curl --fail http://localhost:8000/health/ai
```

Required models are `qwen2.5:3b` and `nomic-embed-text` by default. `/health/ai` must report no
missing models and both `chat_ready` and `embedding_ready` as true. Alternate model names must be
configured in one place and license-reviewed.

Smoke embedding:

```bash
curl --fail http://localhost:11434/api/embed \
  -H 'Content-Type: application/json' \
  -d '{"model":"nomic-embed-text","input":["WorkMate local embedding smoke test"]}'
```

Smoke structured chat/extraction/summarization/classification using `/api/chat` with `format=json`.
No organizational data should be used in initial infrastructure smoke tests.

## 5. Validate deterministic ingestion

The only supported upload is strict UTF-8 OWD Markdown. Use
`backend/tests/fixtures/owd_repository/inbound/receive_shipment_v1_1.md`.

1. Sign in as an admin and list active departments.
2. Upload the fixture for `dept_ops`.
3. Require `compilation_status=SUCCESS` and `deployment_status=PUBLISHED`.
4. Confirm stage source plus workflow/version/state/step/search-metadata rows.
5. Confirm the department semantic cache is invalidated and rebuilt on the next query.
6. Confirm ordinary Markdown returns 422 and PDF/DOCX returns 400 without staging.
7. Confirm an employee upload returns 403.

## 6. End-to-end acceptance

| Scenario | Expected |
| --- | --- |
| Same-department published OWD | Local semantic result and answer with real document/version/step/chunk citation |
| Cross-department query | No evidence leakage; canonical fallback and escalation |
| Draft/archived row | Never indexed or returned under production configuration |
| Ollama embedding outage | Parameterized department/status-scoped SQL retrieval |
| Ollama generation outage | Exact verified extract with real citation |
| Missing/invalid model source IDs | Generated claim rejected; extractive review fallback and escalation |
| Unrelated invented instruction | Rejected; never delivered as grounded guidance |
| No evidence | Canonical fallback and escalation |

## 7. Live-test reporting

Live Snowflake validation requires real credentials and must never be simulated or described as
live. Record account/role names without secrets, exact commands, timestamps, row counts, response
status, same-/cross-department results, latency, and Ollama model revisions. Default unit tests block
unmocked Snowflake connections; opt-in live tests require `WORKMATE_RUN_LIVE_TESTS=1`.
=======
SHOW CORTEX SEARCH SERVICES LIKE 'WORKMATE_KNOWLEDGE_SEARCH'
  IN SCHEMA WORKMATE_AI.KNOWLEDGE_STUDIO;
SELECT AI_COMPLETE('mistral-large2', 'Reply with OK');
```

A failure here is a provisioning or grant problem, even if `/health` reports `database=connected`.

## 5. Validate upload

The current product contract is **strict UTF-8 OWD Markdown only**. PDF, DOCX, text files, and
unstructured Markdown are not accepted. Use
`backend/tests/fixtures/owd_repository/inbound/receive_shipment_v1_1.md` as the canonical smoke
fixture.

1. Sign in as an admin and call `GET /api/v1/knowledge/departments`.
2. Upload the canonical fixture with a returned active department ID.
3. Require `compilation_status=SUCCESS` and `deployment_status=PUBLISHED`.
4. Confirm the staged source with `LIST @...` and confirm rows for the returned workflow/version
   in `workflows`, `workflow_versions`, `workflow_states`, and `workflow_search_metadata`.
5. An ordinary Markdown file must return a structured 422 parser/validator response rather than a
   partial staged or database artifact.

## 6. Validate retrieval before completion

Search with a distinctive phrase from the uploaded fixture and the exact JWT department. The
service target lag is one minute, so allow for refresh before declaring ingestion broken.

```sql
SELECT SNOWFLAKE.CORTEX.SEARCH_PREVIEW(
  'WORKMATE_AI.KNOWLEDGE_STUDIO.WORKMATE_KNOWLEDGE_SEARCH',
  '{"query":"receive shipment","columns":["document_title","department_id","status","search_content"],"filter":{"@and":[{"@eq":{"department_id":"dept_ops"}},{"@eq":{"status":"published"}}]},"limit":5}'
);
```

If direct Search succeeds but Copilot returns no evidence, decode a fresh access token locally and
compare its `department_id` exactly with `workflow_search_metadata.department_id`.

## 7. End-to-end acceptance matrix

| Scenario | Expected result |
| --- | --- |
| Valid OWD, active department | Upload is `SUCCESS` and `PUBLISHED`; stage and compiled rows exist |
| Invalid/unstructured Markdown | Structured 422; no staged or compiled partial artifact |
| Matching query, same department | Grounded answer with document/version/step citations |
| Matching query, different department | Canonical safe fallback; no cross-department citation |
| No matching knowledge | Canonical safe fallback with HTTP 200, even if escalation/n8n/analytics fail |
| Cortex Complete unavailable | Grounded extractive answer from authorized retrieved evidence |
| Cortex Search unavailable | Department-scoped SQL fallback or explicit retrieval failure in logs |

Finish by running the full backend suite and frontend production build. Live Snowflake validation
cannot be replaced by mocked unit tests.
>>>>>>> origin/main
