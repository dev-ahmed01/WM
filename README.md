# WorkMate AI — Enterprise Operational Intelligence Platform

WorkMate AI turns organizational SOPs and policies into state-aware operational guidance with verified citations and analytics.

## Technology

- **Backend:** FastAPI on Python 3.11+
- **Data and AI:** Snowflake Stage, Cortex Search, and Cortex Complete
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
| `automation` | n8n orchestration workflow definitions |
| `ai-services` | Prompt assets and executable grounding evaluations |
| `scripts` | Schema deployment, OWD loading, and verification CLIs |
| `docs` | Architecture, focused remediation notes, and operational guides |

Generated deployment reports belong in the ignored `logs/` directory. TypeScript build state, runtime environment files, caches, and dependency directories must not be committed.

## Prerequisites

- Docker with Docker Compose
- Node.js 18+ and npm
- Python 3.11+
- A Snowflake account with the required database, stage, runtime-role, and Cortex privileges

## Environment setup

Create the ignored backend runtime file from the sanitized template:

```bash
cp backend/.env.example backend/.env
```

Replace every placeholder in `backend/.env`. Use a least-privilege Snowflake runtime role; do not place real credentials in `.env.example` or any tracked document.

For a separately hosted frontend, copy `frontend/.env.example` to `frontend/.env.local` and set its public API base URL.

## Run locally

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
cd frontend
npm run lint
npm run build
```

See [`docs/repository_remediation_plan.md`](docs/repository_remediation_plan.md) for the audited cleanup target and the separate ingestion/Copilot restoration assignment.
