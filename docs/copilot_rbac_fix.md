# Copilot local retrieval, grounding, and RBAC

The previous managed-AI integration has been removed. The active runtime is provider-neutral and
uses Ollama locally, with parameterized Snowflake SQL and deterministic extracts as fallbacks.

## Security invariants

- Department comes only from the authenticated JWT/user record; request bodies cannot override it.
- Snowflake candidates are filtered by exact department and allowed lifecycle status before return.
- Local ranking repeats department/status filtering after ranking.
- Model prompts contain only authorized chunks, with structured Snowflake source IDs.
- Generated source IDs must map to retrieved rows with complete real citation metadata.
- Retrieval similarity is not grounding proof. Claim/evidence support is measured separately.
- Missing IDs, fabricated IDs, unrelated instructions, incomplete metadata, and cross-department
  evidence fail validation and escalate.
- No external managed AI URL is accepted by the local provider.

## Failure behavior

Ollama embedding failure uses deterministic scoped SQL. Ollama generation failure uses a verified
extract. No evidence uses the canonical fallback. Escalation, analytics, and notification failures
are logged without suppressing the validated user response.

See [`local_ai_runtime.md`](local_ai_runtime.md) for index lifecycle and provider setup and
[`snowflake_runtime_runbook.md`](snowflake_runtime_runbook.md) for live validation.
