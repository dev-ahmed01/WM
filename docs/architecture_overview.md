# WorkMate AI system architecture

1. **Frontend — Next.js:** role-specific Knowledge Studio, Copilot, and Intelligence Hub UI.
2. **FastAPI:** JWT/RBAC, deterministic OWD orchestration, local AI providers, validation, workflow state, audit, and escalation.
3. **Snowflake data layer:** the only durable database and OWD source stage. It performs no AI or search-service work.
4. **Ollama local AI:** embeddings and structured grounded runtime generation on private/local infrastructure.
5. **n8n orchestration:** notifications, approvals, schedules, and retries only; never ingestion reasoning or AI.

The deterministic ingestion path is unchanged. The Copilot reads authorized, published Snowflake
candidates, ranks them with a disposable in-memory local index, and passes locally generated output
through mandatory source, grounding, citation, confidence, and department validation. See
[`local_ai_runtime.md`](local_ai_runtime.md).
