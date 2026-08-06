# WorkMate AI — Enterprise Operational Intelligence Platform

WorkMate AI transforms static organizational knowledge (SOPs, manuals, policies) into dynamic operational intelligence using step-aware guidance, verified citations, and automated operational analytics.

## Tech Stack
- **Backend:** FastAPI (Python 3.11+)
- **Database & AI Engine:** Snowflake ONLY (Snowflake Stage, Document AI, Cortex Search, Cortex Embed, Cortex Complete)
- **Frontend:** Next.js 14+ (React, TypeScript, Tailwind CSS, shadcn/ui)
- **Orchestration:** n8n (Triggers, retries, and notifications only — no AI reasoning)
- **Auth:** JWT via FastAPI Security + RBAC (Role and Department scoped)

---

## Getting Started

### 1. Prerequisites
- Docker & Docker Compose
- Node.js 18+ and npm
- Active Snowflake Account with Cortex enabled

### 2. Environment Setup
Copy the configuration template and set your Snowflake credentials:
```bash
cp backend/.env.example backend/.env
```

### 3. Running Backend Locally
Run via Docker Compose:
```bash
docker-compose up --build
```
Or directly using Python:
```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```
API Documentation will be available at http://localhost:8000/docs.

### 4. Running Frontend Locally
```bash
cd frontend
npm install
npm run dev
```
Access the application at http://localhost:3000.
