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

```sql
SELECT CURRENT_ROLE(), CURRENT_DATABASE(), CURRENT_SCHEMA(), CURRENT_WAREHOUSE();
LIST @WORKMATE_AI.KNOWLEDGE_STUDIO.RAW_OWD_STAGE;
SELECT COUNT(*) FROM WORKMATE_AI.SECURITY.departments WHERE is_active = TRUE;
SELECT COUNT(*) FROM WORKMATE_AI.KNOWLEDGE_STUDIO.workflow_search_metadata;
SELECT COUNT(*) FROM WORKMATE_AI.WORKMATE_COPILOT.conversations;
SELECT COUNT(*) FROM WORKMATE_AI.WORKMATE_COPILOT.escalation_records;
SELECT COUNT(*) FROM WORKMATE_AI.INTELLIGENCE_HUB.analytics_events;
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
