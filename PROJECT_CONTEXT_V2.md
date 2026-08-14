# WorkMate AI — As-Built Project Context

Updated: 2026-08-14

This document is the source of truth for the current implementation. It replaces historical
descriptions of abandoned managed-AI, duplicate ingestion, and pre-voice architectures.

## Product definition

WorkMate AI is a state-aware operational guidance platform. Administrators publish structured
Operational Workflow Definition (OWD) Markdown files. Employees receive grounded, step-by-step
text or voice guidance. Managers review adoption, confidence, FAQ, and escalation analytics.

It is not a generic document-chat product. The ingestion boundary intentionally accepts UTF-8
OWD Markdown rather than arbitrary PDF, Word, image, or prose documents.

## Active request flow

```text
Knowledge Studio upload
  -> FastAPI validation
  -> deterministic OWD parse/compile
  -> transactional Snowflake load and source staging
  -> published workflow catalog

Employee text or voice query
  -> JWT and department RBAC
  -> optional Faster-Whisper transcription
  -> optional English/Hindi M2M100 translation
  -> catalog/workflow-state resolution and local Ollama reasoning
  -> mandatory grounding/permission/citation/confidence validation
  -> persisted conversation, workflow state, and analytics
  -> optional Piper/browser speech response
```

## Architecture invariants

1. **One ingestion path.** `knowledge_studio.py` invokes `OWDCompilerPipeline`, which parses,
   validates, compiles, and loads the workflow. Do not add a parallel n8n or alternate writer.
2. **Snowflake is the only durable data platform.** It stores workflow definitions, source-stage
   artifacts, users/RBAC, conversations, workflow sessions, query-resolution memory,
   escalations, voice metadata, and analytics.
3. **Local AI only.** Runtime embeddings and grounded generation use self-hosted Ollama.
   English/Hindi translation uses the bundled quantized M2M100 CTranslate2 provider.
4. **n8n does not reason.** The retained workflow is optional escalation notification delivery.
   It must not parse SOPs, retrieve evidence, generate answers, or write workflow knowledge.
5. **No fake-success or mock-data fallback.** Database/provider failures must be observable.
6. **Workflow state is authoritative.** AI may explain persisted steps but cannot invent or
   mutate graph transitions.
7. **Every employee answer passes validation.** Missing or unauthorized evidence produces the
   canonical grounded fallback and escalation behavior.
8. **Learned query mappings are confirmation-gated.** Only employee-confirmed, department-scoped
   query-to-SOP resolutions may be reused, and the workflow must still be published.

## OWD Markdown

The compiler is deterministic. The grammar is implemented under
`backend/app/compiler/parsers/`; `OWDParser` builds a unified AST, `OWDValidator` enforces the
workflow contract, `OWDCompiler` generates deterministic identifiers, and `OWDLoader` performs
transactional Snowflake writes.

The format supports workflow metadata, states, atomic steps, decisions and options, transitions,
rules, evidence specifications, references, relationships, analytics metadata, user context, and
AI-conversation metadata. Flexible headings and JSON-table authoring are normalized into the same
AST. Upload errors must identify validation problems without staging or partially publishing data.

## Implemented product areas

| Area | Current state |
| --- | --- |
| Authentication/RBAC | JWT access and refresh tokens; Snowflake users, roles, departments; audit middleware |
| Knowledge Studio | OWD upload, compile, publish, list/detail, edit, version history, soft delete, permanent delete |
| Copilot | Catalog matching, grounded retrieval, typo tolerance, workflow state, decisions, pause/resume/abandon, citations and escalation |
| Query memory | Snowflake-backed pending/confirmed/rejected mappings with department scope and published-version validation |
| Voice | English/Hindi recording, Faster-Whisper, M2M100 translation, Piper/deferred speech, protected audio |
| Intelligence Hub | SOP usage, FAQs, confusing procedures, escalations, department adoption, confidence trends |
| Local AI | Ollama chat and embeddings with deterministic scoped SQL/extractive fallbacks |
| n8n | Optional escalation notification webhook only |

## Repository map

- `backend/app/api/v1`: authenticated API routes.
- `backend/app/compiler`: OWD parser, validator, compiler, and loader.
- `backend/app/services`: orchestration and provider-neutral business logic.
- `backend/app/repositories`: Snowflake persistence boundaries.
- `frontend/app` and `frontend/components`: role-specific Next.js UI.
- `analytics/migrations`: the only canonical ordered database schema source.
- `automation/escalation_workflow`: optional n8n notification workflow.
- `ai-services/evals`: executable grounding smoke evaluation.
- `docs`: current architecture and runtime guides.

## Deployment and configuration

- Runtime secrets belong only in ignored `backend/.env` or hosting-provider environment settings.
- Checked-in configuration defaults and examples contain no usable credentials.
- `scripts/deploy_owd_schema.py` applies the canonical ordered Snowflake migrations.
- `backend/scripts/seed_test_users.py` seeds development identities into real Snowflake tables.
- Docker Compose starts Ollama, installs required models, then starts FastAPI and Next.js.
- Vercel can host the frontend, but the FastAPI/Snowflake/Ollama backend still requires a reachable
  long-running host.

## Verification contract

Before release:

1. Run all backend tests from the repository root.
2. Run the grounding evaluation.
3. Run frontend type checking and a production build.
4. Validate every n8n JSON and the Compose configuration.
5. Verify Snowflake connectivity, migrations, test identities, published workflow counts, and
   department isolation.
6. Exercise browser login, Knowledge Studio, Copilot text/voice, workflow progression/history,
   permanent deletion, and Intelligence Hub for the appropriate roles.
7. Scan tracked content for credentials and generated artifacts before pushing.

## Explicitly out of scope

- OCR and arbitrary PDF/DOCX/image ingestion.
- Managed Snowflake AI/search services.
- A second database, vector store, or ingestion pipeline.
- Jira or other ticketing integration unless separately authorized.
- n8n-based reasoning, retrieval, or knowledge writes.

When architecture changes materially, regenerate this document from the current code, migrations,
tests, and runbooks rather than preserving contradicted historical statements.
