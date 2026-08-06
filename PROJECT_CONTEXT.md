# WorkMate AI — Project Context & Single Source of Truth

> **FROZEN CONTEXT DOCUMENT**
> This document is the single source of truth for the WorkMate AI platform architecture, requirements, stack rules, and implementation scope. All AI agents and human developers MUST strictly adhere to this file.

---

## 1. Project Overview
WorkMate AI is an Enterprise Operational Intelligence Platform designed to transform static corporate documentation (SOPs, manuals, policies) into interactive, step-aware guidance for frontline employees and operational staff.

Unlike standard QA chatbots, WorkMate AI maintains procedural workflow state across interactions, deterministically guiding employees through complex operational steps while enforcing strict grounding, department-scoped permissions, and confidence validation.

---

## 2. Confirmed Tech Stack & Scope Boundaries

### Confirmed Stack (Non-Negotiable)
- **Backend Framework**: FastAPI (Python 3.11+)
- **Database & Data Platform**: **Snowflake ONLY**
  - Structured data: Relational SQL tables (`users`, `knowledge_items`, `knowledge_versions`, `knowledge_chunks`, `conversations`, `conversation_messages`, `workflow_sessions`, `escalations`, `analytics_events`)
  - Document storage: Snowflake Stage (`@RAW_OWD_STAGE`)
  - OCR & Parsing: Document AI (with Python fallback)
  - Semantic Chunking: Windowed semantic chunker
  - Embeddings: Snowflake Cortex Embed (`cortex_embed_e5_base_v2`)
  - Vector Search: Snowflake Cortex Search Index
  - LLM Reasoning: Snowflake Cortex Complete
- **Frontend Framework**: Next.js (React) + TypeScript + Tailwind CSS + shadcn/ui
- **Orchestration**: n8n (triggers/retries/notifications/scheduling ONLY — n8n never performs AI reasoning)
- **Authentication**: JWT via FastAPI Security + RBAC (role + department scoped)
- **Deployment**: Docker, Vercel (frontend), Render/Railway (backend)

### Explicitly Excluded Technologies
- No PostgreSQL
- No MongoDB
- No Redis
- No Java / Spring Boot
- No separate vector database vendor (e.g. Pinecone, Weaviate, Qdrant) — everything AI/data related lives in Snowflake.

---

## 3. The Three Core Modules

### 1. Knowledge Studio (Admin)
Enterprise knowledge ingestion & versioning pipeline:
`Upload Document` $\rightarrow$ `Validate (type & <=25MB)` $\rightarrow$ `Snowflake Stage Upload` $\rightarrow$ `n8n Webhook Trigger` $\rightarrow$ `Document AI Parse/OCR` $\rightarrow$ `Semantic Chunking` $\rightarrow$ `Cortex Embed Generation` $\rightarrow$ `Cortex Search Index Update` $\rightarrow$ `Publish`.

### 2. WorkMate Copilot (Employee)
Step-aware operational guidance assistant:
`Employee Message` $\rightarrow$ `Intent Detection & Ambiguity Check` $\rightarrow$ `Active SOP State Resolution` $\rightarrow$ `Department-Scoped Cortex Search` $\rightarrow$ `Context Assembly` $\rightarrow$ `Cortex Complete Generation` $\rightarrow$ `Response Validation Gate (Grounding, Permissions, Citations, Confidence)` $\rightarrow$ `Escalation if Low Confidence` $\rightarrow$ `Telemetry Recording` $\rightarrow$ `Response Delivery`.

### 3. Intelligence Hub (Manager)
Read-only managerial analytics dashboard reading from low-latency Snowflake BI materialized views (`V_ANALYTICS_*`):
`SOP Usage`, `FAQs`, `Confusing Procedures`, `Escalation Logs`, `Department Adoption`, `Confidence Score Trends`.

---

## 4. Mandatory Architectural Rules

1. **Response Validation Layer Pre-Delivery Gate**:
   - Runs on EVERY Copilot response without bypass.
   - Enforces grounding verification, department permission checks, citation generation, and confidence scoring ($<0.70$ or ungrounded triggers escalation).
   - Zero-hallucination canonical fallback phrasing:
     > *"I could not find verified organizational guidance for this request. Please contact your supervisor or administrator. The closest related documentation is provided below."*
2. **Strict Separation of Reasoning and Orchestration**:
   - n8n orchestrates events, retries, and notifications.
   - FastAPI + Snowflake Cortex perform all AI reasoning, semantic retrieval, embeddings, and LLM text generation.
3. **Deterministic Procedural Navigation Engine**:
   - `get_next_action()` in `WorkflowStateService` indexes strictly into actual retrieved SOP step lists. It NEVER delegates step generation or next-step selection to an LLM.
4. **Data Isolation & Scope**:
   - Only `PUBLISHED` document versions are retrievable by employees.
   - All retrieval is strictly scoped to the caller's `department_id` (admins bypass).

---

## 5. Current Development Status (Phase 1 – Phase 8 Fully Completed)

| Module / Area | Implementation & Verification Status |
|---|---|
| **Phase 1: Project Architecture & Context** | Single source of truth locked in `PROJECT_CONTEXT.md` and `.agents/AGENTS.md`. |
| **Phase 2: Auth & RBAC Security** | Implemented `security.py`, `auth_middleware.py`, `rbac_middleware.py`, `POST /login`, `POST /refresh`, `GET /me`. Verified with test suite. |
| **Phase 3 & 4: Knowledge Studio & Pipeline** | Implemented `knowledge_studio.py`, `internal_ingestion.py`, Document AI/OCR fallback parser, windowed semantic chunker, `CortexClient` (embed & search index), `X-Internal-Token` n8n webhook authentication. Verified with test suite. |
| **Phase 5: Copilot Retrieval & Validation** | Implemented `retrieval.py` (published & department-scoped chunk search), `validation.py` (mandatory pre-delivery gate with canonical fallback). Verified with test suite. |
| **Phase 6: Workflow State Engine** | Implemented `workflow_state.py` backed by Snowflake `workflow_sessions` table (`get_active_session`, `start_session`, `mark_step_complete`, `pause_session`, `resume_session`, `abandon_session`, `get_next_action` deterministic state machine) and `POST /copilot/session/{id}/resume`. Verified with test suite. |
| **Phase 7: Full Orchestration & Real Escalations** | Extended `POST /copilot/message` with intent detection, clarification short-circuit, active SOP step progression, real `escalation.py` triggering (`escalations` table + n8n webhook), `analytics_service.py` telemetry logging (`analytics_events`), and frontend connection in Next.js `CopilotPage`. Verified with 100% test pass rate. |
| **Phase 8: Intelligence Hub Analytics** | Created Snowflake BI views (`V_ANALYTICS_*`) in `analytics/` folder, implemented manager-only `/api/v1/analytics/*` router (`sop-usage`, `faqs`, `confusing-procedures`, `escalations`, `department-adoption`, `confidence-trends`), and connected real data calls to Next.js `IntelligenceHubPage`. Verified with 100% test pass rate. |

---

## 6. Glossary & Key References
- **SOP**: Standard Operating Procedure.
- **Response Validation Layer**: Mandatory pre-delivery gate checking grounding, permissions, citations, confidence score.
- **Workflow State Engine**: Deterministic state machine tracking employee progress through SOP steps (`workflow_sessions`).
- **Cortex**: Snowflake AI platform (Cortex Search, Cortex Embed, Cortex Complete).
- **Intelligence Hub**: Manager dashboard powered by Snowflake BI views (`analytics/` folder SQL).
