# WorkMate AI system architecture

<<<<<<< HEAD
1. **Frontend — Next.js:** role-specific Knowledge Studio, Copilot, and Intelligence Hub UI.
2. **FastAPI:** JWT/RBAC, deterministic OWD orchestration, local AI providers, validation, workflow state, audit, and escalation.
3. **Snowflake data layer:** the only durable database and OWD source stage. It performs no AI or search-service work.
4. **Ollama local AI:** embeddings and structured grounded runtime generation on private/local infrastructure.
5. **n8n orchestration:** notifications, approvals, schedules, and retries only; never ingestion reasoning or AI.

The deterministic ingestion path is unchanged. The Copilot reads authorized, published Snowflake
candidates, ranks them with a disposable in-memory local index, and passes locally generated output
through mandatory source, grounding, citation, confidence, and department validation. See
[`local_ai_runtime.md`](local_ai_runtime.md).
=======
WorkMate AI operates on a multi-layered architecture:
1. **Frontend Layer (Next.js 14):** Provides role-tailored interfaces for Knowledge Studio (Admins), Copilot (Employees), and Intelligence Hub (Managers).
2. **API & Reasoning Layer (FastAPI):** Controls JWT authentication, RBAC policy enforcement, procedural workflow state management, and coordinates LLM calls.
3. **Data Layer (Snowflake):** The single durable persistence layer for relational data and raw OWD staging. Cortex capabilities are optional and disabled by default.
4. **Local AI Layer (FastAPI-managed):** Optional self-hosted retrieval and generation providers run outside Snowflake; deterministic SQL retrieval and extractive answers remain the zero-AI baseline.
5. **Automation & Orchestration Layer (n8n):** Handles asynchronous triggers, background notifications, and ingestion schedules. n8n does not perform AI reasoning.

See [`cortex_replacement_options.md`](cortex_replacement_options.md) for the provider decision, self-hosted alternatives, licensing cautions, and migration sequence.
>>>>>>> origin/main
