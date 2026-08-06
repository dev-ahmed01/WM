# WorkMate AI System Architecture Overview

WorkMate AI operates on a multi-layered architecture:
1. **Frontend Layer (Next.js 14):** Provides role-tailored interfaces for Knowledge Studio (Admins), Copilot (Employees), and Intelligence Hub (Managers).
2. **API & Reasoning Layer (FastAPI):** Controls JWT authentication, RBAC policy enforcement, procedural workflow state management, and coordinates LLM calls.
3. **Data & AI Layer (Snowflake):** The single persistence layer for relational storage, raw OWD staging (Snowflake Stage), semantic search (Cortex Search), and Copilot answer generation (AI_COMPLETE).
4. **Automation & Orchestration Layer (n8n):** Handles asynchronous triggers, background notifications, and ingestion schedules. Reasoning is strictly handled by FastAPI + Cortex.
