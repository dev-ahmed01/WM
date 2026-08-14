# WorkMate AI — Enterprise Operational Intelligence Platform

WorkMate AI turns organizational SOPs and policies into state-aware operational guidance with verified citations and analytics.

## Technology

- **Backend:** FastAPI on Python 3.11+
- **Data:** Snowflake relational storage and OWD source Stage only
- **Local AI:** self-hosted Ollama embeddings and grounded generation, with SQL/extractive fallbacks
- **Frontend:** Next.js, React, TypeScript, and Tailwind CSS
- **Orchestration:** n8n for triggers, retries, approvals, and notifications only
- **Security:** JWT authentication with role- and department-scoped access

## Repository map

| Path | Responsibility |
| --- | --- |
| `backend/app/api` | Versioned FastAPI routes |
| `backend/app/services` | Ingestion, retrieval, validation, workflow state, and analytics logic |
| `backend/app/repositories` | Snowflake persistence boundaries |
| `backend/app/compiler` | Deterministic OWD parser, validator, compiler, and loader |
| `backend/tests` | Backend unit and orchestration regression tests |
| `frontend/app` | Next.js pages and route groups |
| `frontend/components` | Reusable UI, chat, dashboard, and upload components |
| `analytics/migrations` | Ordered Snowflake schema and service migrations |
| `automation` | Optional n8n notification workflow definitions |
| `ai-services` | Executable grounding evaluations |
| `scripts` | Schema deployment, OWD loading, and verification CLIs |
| `docs` | Architecture, focused remediation notes, and operational guides |

Generated deployment reports belong in the ignored `logs/` directory. TypeScript build state, runtime environment files, caches, and dependency directories must not be committed.

## Prerequisites

- Docker with Docker Compose
- Node.js 20.9+ and npm
- Python 3.11+
- A Snowflake account with database, stage, and least-privilege runtime access
- Enough local disk/RAM for the configured Ollama models

## Environment setup

Create the ignored backend runtime file from the sanitized template:

```bash
cp backend/.env.example backend/.env
```

Fill every blank credential in `backend/.env`. Use a least-privilege Snowflake runtime role; do not place real credentials in `.env.example` or any tracked document.

For a separately hosted frontend, copy `frontend/.env.example` to `frontend/.env.local` and set its public API base URL.

## Run locally

### Self-hosted local AI

The normal Compose startup launches Ollama, health-checks it, idempotently installs the configured
chat and embedding models, and then starts FastAPI:

```bash
docker compose up --build
curl --fail http://localhost:8000/health/ai
```

For host-native or explicit setup:

```bash
# For a host-native backend, set LOCAL_AI_BASE_URL=http://127.0.0.1:11434 in backend/.env.
scripts/setup_local_ai.sh host
scripts/setup_local_ai.sh compose
# Windows: .\scripts\setup_local_ai.ps1 -Mode Host
```

All inference stays on the configured local/private Ollama service. If Ollama becomes unavailable,
Copilot uses department-scoped SQL retrieval and verified extractive responses.

### Docker Compose

```bash
docker compose up --build
```

### Backend without Docker

Run from the repository root so scripts and tests resolve their root-relative imports consistently:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r backend/requirements.txt
PYTHONPATH=backend uvicorn app.main:app --reload --port 8000
```

API documentation is available at <http://localhost:8000/docs>.

### Frontend

```bash
cd frontend
npm ci
npm run dev
```

The frontend is available at <http://localhost:3000>.

## Database setup and test users

Deploy the Snowflake schema with the deployment CLI, then seed local test identities with the single canonical seed script:

```bash
PYTHONPATH=.:backend python scripts/deploy_owd_schema.py
PYTHONPATH=.:backend python backend/scripts/seed_test_users.py
```

These commands access Snowflake using `backend/.env`. Review the SQL migrations and role grants before running them outside a development account.

## Validation

```bash
PYTHONPATH=.:backend python -m pytest -q backend/tests
PYTHONPATH=backend python ai-services/evals/grounding_test.py
npx --yes pyright@latest
cd frontend
npm run typecheck
npm run build
```

See [`docs/local_ai_runtime.md`](docs/local_ai_runtime.md) for provider, index, grounding, model,
health, hardware, and fallback behavior. Use the
[`Snowflake runtime runbook`](docs/snowflake_runtime_runbook.md) for database/stage and live
same-/cross-department validation.

See [`docs/multilingual_voice.md`](docs/multilingual_voice.md) for Faster-Whisper, Ollama
translation, Piper voices, language configuration, protected audio delivery, and voice analytics.
