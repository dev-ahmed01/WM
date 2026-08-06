# WorkMate AI System Architecture Overview

WorkMate AI operates on a multi-layered architecture:
1. **Frontend Layer (Next.js 14):** Provides role-tailored interfaces for Knowledge Studio (Admins), Copilot (Employees), and Intelligence Hub (Managers).
2. **API & Reasoning Layer (FastAPI):** Controls JWT authentication, RBAC policy enforcement, procedural workflow state management, and coordinates LLM calls.
3. **Data & AI Layer (Snowflake):** The single persistence layer for relational storage, raw file staging (Snowflake Stage), OCR (Document AI), semantic search (Cortex Search), vector embeddings (Cortex Embed), and LLM reasoning (Cortex Complete).
4. **Automation & Orchestration Layer (n8n):** Handles asynchronous triggers, background notifications, and ingestion schedules. Reasoning is strictly handled by FastAPI + Cortex.
