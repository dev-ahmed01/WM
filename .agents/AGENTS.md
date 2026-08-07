# WorkMate AI — Project Architecture & Rules (FROZEN CONTEXT)

All AI agents working on this codebase MUST strictly adhere to the single source of truth defined in [PROJECT_CONTEXT_V2.md](../PROJECT_CONTEXT_V2.md).

## Non-Negotiable Core Principles & Architecture Rules

1. **Shift to Operational Guidance (Not Stateless RAG)**:
   - WorkMate AI is NOT a one-shot Q&A bot. It is a procedural, state-aware guidance system that tracks where an employee is within an SOP or workflow.
   - Always preserve and track `Workflow State` across interactions.

2. **Strict Separation of Reasoning and Orchestration**:
   - **n8n**: Responsible ONLY for workflow orchestration (triggering ingestion pipelines, retries, approvals, notifications, scheduling, integration triggers). n8n MUST NOT perform AI reasoning, embedding generation, semantic retrieval, or LLM summarization.
   - **Snowflake Cortex & FastAPI**: All AI reasoning, semantic processing, OCR/parsing, chunking, embeddings generation, vector search (Cortex Search), and LLM completion (Cortex Complete) MUST live in Snowflake Cortex / FastAPI backend services.

3. **Data Platform Unification**:
   - **Snowflake** is the single database and storage platform for documents (Snowflake Stage), embeddings, conversation memory, analytics, and versioned knowledge. Do not introduce secondary databases without explicit authorization.

4. **Response Validation Layer (Mandatory Pre-Delivery Gate)**:
   - Before ANY response reaches an employee, it MUST pass through the Response Validation Layer:
     1. Grounding Verification
     2. Department/RBAC Permission Check
     3. Citation Generation (Document + Version + Step)
     4. Confidence Score Estimation
   - Zero-hallucination policy: If confidence is below threshold or evidence is missing, fall back to canonical phrasing:
     > *"I could not find verified organizational guidance for this request. Please contact your supervisor or administrator. The closest related documentation is provided below."*

5. **Event-Driven Knowledge Ingestion**:
   - Knowledge upload processing is strictly event-driven (Upload → FastAPI → Snowflake Stage → n8n trigger → Ingestion Service → Cortex Processing → Search Index update). Do not refactor into polling or batch jobs.

6. **Scope Boundaries**:
   - **MVP**: Knowledge Studio, WorkMate Copilot (chat), Intelligence Hub, Auth/RBAC + Audit Logging, n8n Ingestion Orchestration.
   - **Post-MVP / Deferred**: Knowledge Graph, Voice/TTS integration, Jira integration, unless explicitly updated via official PRD/architecture doc.
