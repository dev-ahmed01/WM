# WorkMate AI System Architecture Overview

WorkMate AI operates on a multi-layered architecture:
1. **Frontend Layer (Next.js 14):** Provides role-tailored interfaces for Knowledge Studio (Admins), Copilot (Employees), and Intelligence Hub (Managers).
2. **API & Reasoning Layer (FastAPI):** Controls JWT authentication, RBAC policy enforcement, procedural workflow state management, and coordinates LLM calls.
3. **Data Layer (Snowflake):** The single durable persistence layer for relational data and raw OWD staging. Cortex capabilities are optional and disabled by default.
4. **Local AI Layer (FastAPI-managed):** Optional self-hosted retrieval and generation providers run outside Snowflake; deterministic SQL retrieval and extractive answers remain the zero-AI baseline.
5. **Automation & Orchestration Layer (n8n):** Handles asynchronous triggers, background notifications, and ingestion schedules. n8n does not perform AI reasoning.

See [`cortex_replacement_options.md`](cortex_replacement_options.md) for the provider decision, self-hosted alternatives, licensing cautions, and migration sequence.
