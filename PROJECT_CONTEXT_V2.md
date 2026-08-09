# PROJECT_CONTEXT_V2.md — WorkMate AI

> **Architecture decision (2026-08-09):** Snowflake is the durable database and
> OWD source stage only. All managed Snowflake AI/search code, settings, migrations,
> and grants have been removed. Runtime embeddings and grounded generation use
> self-hosted Ollama; a disposable in-memory semantic index and scoped SQL/extractive
> fallbacks preserve operation. See `docs/local_ai_runtime.md`. This decision
> supersedes older historical statements below.

**Purpose of this document:** The original `PROJECT_CONTEXT.md` describes the
**intended architecture** from the initial product/vision doc. It was written
before implementation and was never updated as the team actually built the
system. During implementation the project **pivoted significantly** — a
different core pipeline was built, several planned features were never
started, and (until a recent audit/fix pass) the codebase had two parallel,
conflicting ingestion pipelines due to that pivot never being fully cleaned
up.

This document is the **as-built source of truth**. It exists so any AI
assistant (ChatGPT, Claude, Copilot, Cursor, etc.) picking up this project
understands what is *actually running today*, not what was originally
planned. Where the original vision and the real system diverge, both are
stated explicitly so nobody "fixes" the real system back toward a plan that
was abandoned on purpose, and nobody assumes a feature exists because it was
in the original doc.

**Status as of this document:** Backend has just been through a full
architectural audit and cleanup pass (see §7). All known critical bugs from
that pass are fixed and the codebase compiles cleanly. Submission deadline
was imminent at time of writing — treat anything marked "not yet verified"
as the top priority before demoing.

---

## 1. What This Project Actually Is (real, current definition)

WorkMate AI, as built, is **not** the general-purpose "upload any document,
AI parses/OCRs/categorizes/summarizes it, chat with everything" platform
described in the original vision doc. It is currently:

**A structured Markdown-DSL compiler + execution engine for Operational
Workflow Definitions (OWDs), plus a RAG-lite copilot chat layer on top.**

In practice:
- Administrators upload a `.md` file written in a specific internal
  directive syntax (state blocks, step blocks, decision/rule blocks,
  metadata front-matter — see §4).
- A deterministic compiler (not an LLM) parses that markdown into an AST,
  validates it, compiles it into a relational workflow graph (states, steps,
  transitions, rules), and loads it into Snowflake.
- Employees converse with a Copilot that retrieves from that compiled
  workflow graph (scoped SQL by default, or an optional search provider) and tracks which step/state the employee is
  currently on.
- Managers see analytics dashboards sourced from conversation + workflow
  data.

This is a **narrower, more deterministic** system than the original vision.
That's a legitimate architectural choice (deterministic compilation is more
reliable and auditable than "AI categorizes and summarizes your PDF"), but
it means most of the original ingestion pipeline (OCR, AI categorization, AI
summarization, department auto-identification) **was never built** — it was
replaced by a compiler.

---

## 2. Original Vision vs. What Was Actually Built

| Area | Original vision (`PROJECT_CONTEXT.md`) | What's actually built |
|---|---|---|
| **Core ingestion model** | Upload any document type → OCR → AI categorization → AI summarization → department tagging → semantic chunking → embeddings | Upload a **markdown file written in a specific OWD directive syntax** → deterministic parse → AST → compile → MERGE into Snowflake relational tables. No OCR, no AI summarization, no AI categorization at ingest time. |
| **File type handling** | PDF, DOCX, manuals, flowcharts, etc. | Upload endpoint accepts only UTF-8 `.md` and requires OWD directives. PDF/DOCX/TXT/OCR and arbitrary prose are not supported. |
| **"AI Categorization" / "AI Summary" pipeline stages** | Explicit pipeline stages performed by Cortex during ingestion | Not implemented. The compiler is deterministic (regex/AST-based parsing), not LLM-based, at ingest time. |
| **Knowledge Graph** | Explicitly listed as a *future* enhancement, cross-document | A **relationship parser** exists (`compiler/parsers/relationship_parser.py`) that parses Parent/Child/Related/Previous/Next/Escalation/Exception SOP references *within a single OWD document's metadata*. This is a building block, not the enterprise-wide knowledge graph described in the vision doc — still not built at that scope. |
| **Voice input (Whisper)** | Listed as a supported interaction mode | **Not implemented anywhere in the codebase.** No Whisper integration, no audio upload/transcription endpoint, nothing. Confirmed via full-repo search — zero references. |
| **Text-to-Speech (ElevenLabs/OpenAI TTS)** | Listed as optional stack component | **Not implemented anywhere.** Zero references in the codebase. |
| **Multilingual conversation support** | Listed as a supported interaction method | **Not implemented anywhere.** No language-detection or translation layer exists. There is no translation or explicit multilingual handling logic. |
| **`ai-services/` directory** | Not named as such in the original doc, but implied by "AI reasoning lives in backend services" | Exists but is minimal: two prompt template `.txt` files (`copilot_procedural.txt`, `validation_grounding.txt`) and one eval script (`grounding_test.py`). No standalone AI service layer beyond that — prompt building actually happens inline in `services/retrieval.py` / `services/validation.py`, not as a separate service module. |
| **n8n orchestration** | Orchestration-only (ingestion triggers, retries, notifications, approvals, scheduling) — explicitly must not do AI reasoning | **Historically violated this rule.** A legacy n8n-driven ingestion pipeline (`internal_ingestion.py` + `automation/ingestion_workflow/`) existed in parallel with the real OWD compiler and independently wrote to a separate legacy table family (`knowledge_chunks`). This has just been **deleted** (see §7) — n8n is currently only wired to `escalation_workflow`, `maintenance_workflow`, and `versioning_workflow`, which is closer to the intended orchestration-only role. |
| **Response Validation Layer (grounding/permission/citation/confidence gate)** | Mandatory pre-delivery gate, explicit pipeline stage | **Implemented** — `services/validation.py` (`ResponseValidationService`) exists and is wired into the copilot message endpoint, alongside `services/retrieval.py`, `services/workflow_state.py`, and `services/escalation.py`. This part of the vision was actually built close to spec. |
| **Workflow State Tracking / Procedural Navigation** | Core differentiator — track which SOP/step employee is on | **Implemented** — `services/workflow_state.py` + `repositories/owd_repository.py` (read paths: `get_initial_state`, `get_steps_for_state`, `get_next_state_transition`) drive this. This part matches the vision. |
| **Escalation Engine** | Routes low-confidence responses to a human, optional Jira integration | **Partially implemented.** `services/escalation.py` and `api/v1/escalations.py` exist. Jira integration is a known TODO/stub (matches the original doc's "optional" framing — this one is *not* a divergence, it was correctly scoped as optional and left unbuilt). |
| **Auth/RBAC/JWT** | JWT auth, RBAC, department scoping, audit logging | **Implemented** — `middleware/auth_middleware.py`, `middleware/rbac_middleware.py`, `middleware/audit_logger.py`, real Snowflake-backed `SECURITY.users`/`roles`/`user_roles` tables. Matches the vision. Audit logging writes to a real `AUDIT_LOG` Snowflake table (mock fallback was just removed — see §7). |
| **Frontend** | Next.js + TypeScript, Tailwind + shadcn/ui, chat/voice UI, admin UI, manager dashboards | **Implemented for chat/admin/dashboards; no voice UI** (matches the "voice not implemented" gap above). All frontend↔backend API wiring was checked and is correct — no broken links. |

---

## 3. Why the Pivot Happened (inferred from code, not documented anywhere)

There is no written decision record for this pivot — it's inferred from the
codebase itself. What the evidence shows:

- The project moved from "ingest arbitrary enterprise documents with AI" to
  "compile a strict internal markdown DSL deterministically" at some point.
- This is a reasonable engineering decision for a hackathon/MVP timeline —
  deterministic compilation is far easier to get *correct and demoable* in
  limited time than a full AI-driven OCR/categorization/summarization
  pipeline, and it produces auditable, structured output (exact states,
  steps, transitions) rather than fuzzy AI-generated structure.
- **The problem was not the pivot itself — it's that the old pipeline was
  never deleted.** Both the old (legacy n8n → `knowledge_chunks` table
  family) and new (OWD compiler → `KNOWLEDGE_STUDIO.*` tables) paths stayed
  wired into the same upload endpoint, running on every single upload,
  writing to different tables, and racing each other to set the same
  `status` field. This produced exactly the kind of "it looks published but
  the data doesn't match" symptoms that triggered the audit in §7.

**Going forward:** if another pivot happens, delete the old path in the same
change that introduces the new one. Do not leave two implementations wired
into the same endpoint "just in case."

---

## 4. The OWD Markdown DSL (the actual core artifact of this system)

This is the single most important thing for any AI assistant to understand
before touching ingestion code, because it's not documented anywhere else
and doesn't match the original vision doc at all.

- Administrators upload a `.md` file.
- The file must contain **directive blocks** recognized by the parser
  suite in `backend/app/compiler/parsers/`: at minimum `state` blocks
  (parsed by `state_parser.py`) and `step` blocks (parsed by
  `step_parser.py`), plus decision, rule, evidence, and relationship
  blocks handled by their respective parser modules.
- There is YAML-style metadata front-matter (relationship_parser.py uses
  `yaml` to parse Parent/Child/Related/Previous/Next SOP references from
  it).
- `ASTBuilder` (`compiler/parsers/ast_builder.py`) composes all sub-parser
  output into a `UnifiedAST`.
- `OWDParser` (`compiler/parser.py`) is the facade that orchestrates
  `ASTBuilder`.
- `compiler.py` walks the AST and generates **deterministic UUIDs** (via
  `generate_deterministic_uuid`) for every workflow, version, state, and
  step — not random UUIDs and not `item_xxx`/`ver_xxx` style string IDs
  (those only ever appeared in unit test fixtures, never in real output).
- `loader.py` transactionally `MERGE`s the compiled structures into
  `KNOWLEDGE_STUDIO.workflows`, `workflow_versions`, `workflow_states`,
  `workflow_steps`, `workflow_transitions`.

**If you need the exact directive grammar** (precise bracket/block syntax),
read `backend/app/compiler/parsers/*.py` directly — this document
intentionally doesn't guess at exact syntax it can't verify with 100%
confidence from a single pass.

**Practical implication:** if you want to upload a real SOP today, it must
be hand-authored (or generated) in this OWD markdown format. You cannot
hand it a plain prose PDF/Word SOP and expect it to work — that gap (no
OCR/prose-to-structure conversion) is real and currently unaddressed.

---

## 5. Actual Module/Feature Status (MVP scope from original §5.1, graded against reality)

| Original MVP item | Status |
|---|---|
| Knowledge Studio — upload, ingestion pipeline | ✅ Built, but as the OWD compiler described in §4, not the OCR/AI-categorization pipeline originally described |
| WorkMate Copilot — chat, intent detection, workflow state, grounded retrieval, escalation | ✅ Built and reasonably close to spec (retrieval, workflow state, validation, escalation are all real services) |
| WorkMate Copilot — Voice, Multilingual | ❌ Not built at all |
| Intelligence Hub — manager dashboards | ✅ Built — `api/v1/intelligence.py` exposes sop-usage, faqs, confusing-procedures, escalations, department-adoption, confidence-trends; frontend consumes all of them correctly |
| Auth & RBAC | ✅ Built, real Snowflake-backed, JWT, audit logging |
| Automation layer (n8n) | ⚠️ Built, but was doing more than orchestration (running a parallel legacy ingestion pipeline) until the recent cleanup. Now scoped down to escalation/maintenance/versioning workflows only. |

---

## 6. Technology Stack — Actual vs. Original

Mostly matches the original table (§11 of `PROJECT_CONTEXT.md`) with these
corrections:

- **LLM/AI reasoning:** Runtime AI is self-hosted through
  `backend/app/integrations/ai_gateway.py` and `local_ai_provider.py`. Snowflake
  remains data/stage only. Provider failure falls back to scoped SQL retrieval
  and deterministic extractive answers.
- **Voice/TTS/Multilingual stack rows** (Whisper, ElevenLabs/OpenAI TTS):
  accurately still "optional/future" per the original doc, but should now
  be understood as **0% started**, not partially started.
- **Deployment target** (Docker + Vercel + Render/Railway): not verified in
  this pass — no deployment manifests were audited for correctness. Treat
  as unverified.

---

## 7. Recent Architectural Audit & Fix Pass (institutional memory — read before touching backend/)

A full forensic audit was performed on the codebase shortly before
submission, followed by a direct fix pass. This section exists so nobody
re-discovers or re-introduces these issues.

### Root causes found and fixed
1. **Silent fake-success on Snowflake write failure.** `compiler/loader.py`
   used to catch any Snowflake insert exception and, if `APP_ENV=="dev"`,
   silently write to an in-memory mock store and return `success=True`
   anyway — meaning the API could report "published" while nothing was
   actually persisted. **Fixed:** now always raises a real exception on
   failure.
2. **A full legacy parallel ingestion pipeline was still live.** A second
   upload-adjacent flow (`api/v1/internal_ingestion.py`, triggered via an
   n8n webhook after every real upload) wrote toward the old
   `knowledge_chunks` table family — the exact thing the OWD migration was
   supposed to replace. It depended on a whole separate `knowledge-engine/`
   parser directory and a duplicate managed-AI client implementation. **Fixed:**
   this entire path — the router, the n8n workflow JSON, the
   `knowledge-engine/` directory, the duplicate managed-AI client, the dead
   `admin.py` stub, and the callback endpoint that received its status
   updates — was deleted.
3. **Race condition on `workflow_versions.status`.** Because both pipelines
   fired on every upload, the real compiler would set `status='published'`
   synchronously, and the legacy n8n callback chain would later
   asynchronously overwrite the same field with `'staged'`/`'parsed'`/etc.
   This produced intermittent, timing-dependent "why does this sometimes
   show published and sometimes not" symptoms. **Fixed** as a side effect
   of removing the legacy pipeline (only one writer remains).
4. **Pervasive mock-data fallback (`USE_MOCK_DB`).** Six files
   (`config.py`, `knowledge_repository.py`, `user_repository.py`,
   `conversation_repository.py`, `analytics_service.py`,
   `audit_logger.py`) had branches that would silently substitute
   in-memory mock data for real Snowflake reads/writes, either
   unconditionally (`USE_MOCK_DB=True`, which was the **default** in
   `config.py`) or as a silent fallback whenever a real Snowflake call
   failed in `dev` environment. **Fixed:** all 25 mock/fallback branches
   across those 6 files were removed. Every code path now either performs
   the real Snowflake operation or raises a real error — nothing is
   silently faked.
5. **Snowflake connection schema mismatch.** `.env` had
   `SNOWFLAKE_SCHEMA=PUBLIC` even though every query in the codebase is
   fully-qualified against `KNOWLEDGE_STUDIO.*`. Changed default to
   `KNOWLEDGE_STUDIO` for consistency. **Not independently verified**
   that the schema and grants exist in the live Snowflake account — this
   is the one item that needs a human (or an assistant with live Snowflake
   access) to confirm.
6. **Minor cleanup:** legacy `KNOWLEDGE_STAGE` stage name renamed to
   `RAW_OWD_STAGE`; stray debug `print()` statements removed from two
   parser files; a dead, never-called duplicate persistence method
   (`owd_repository.py::save_compiled_workflow`) removed.

### Consequence you must know about
Because the mock user-login fallback was removed from `user_repository.py`,
**real users must exist in Snowflake's `SECURITY.users` table** for login
to work — there is a real seed script for this:
`backend/scripts/seed_test_users.py` (does a genuine Snowflake `MERGE`, not
a mock). Run it before assuming login is broken.

### Verified clean (checked during the audit, no action needed)
- All frontend↔backend API call sites match real registered routes exactly.
- Snowflake connection layer (`core/database.py`) has a single, correct
  connection implementation.
- `compiler/parser.py` is a legitimate facade over the modular
  `compiler/parsers/*` sub-parsers, not a duplicate implementation.
- `backend/app/integrations/ai_gateway.py` is the provider-neutral runtime AI gateway.

### Known remaining debt (not yet cleaned up, lower priority)
- `api/v1/knowledge_studio.py`'s `upload_knowledge` endpoint still contains
  a large block of "FORENSIC INSPECTION" debug logging (filename, byte
  count, SHA-256 hash, directive counts) left over from the original bug
  investigation. Not harmful, just noisy — candidate for removal once the
  system is stable.
- No OCR/binary-document parsing exists. The endpoint correctly restricts uploads to strict UTF-8 OWD `.md`.

---

## 8. Pending Decisions (carried over from original doc, still unresolved)

All six items from the original `PROJECT_CONTEXT.md` §25 remain genuinely
unresolved — nothing in the recent audit touched these:

1. Voice input (Whisper) / multilingual — MVP or phase 2? Given zero
   implementation exists, this is effectively already phase 2 by default
   unless someone actively decides otherwise.
2. Text-to-Speech — same as above, zero implementation.
3. Formal database schema documentation — still doesn't exist as a
   standalone doc; the real schema must be reverse-engineered from
   `backend/app/repositories/*.py` and `scripts/deploy_owd_schema.py` if
   needed.
4. API versioning/error-handling conventions — the API does use `/api/v1/`
   prefixing in practice, but this was never written down as a decided
   convention.
5. Security specifics (encryption, secrets management, token expiry, PII
   retention) — still undecided. Note: `.env` currently has real secrets
   (Snowflake password, JWT secret) committed in plaintext — fine for a
   hackathon repo kept private, but flag before any public repo push.
6. Jira integration for escalation — still correctly scoped as optional,
   still unbuilt.

**New pending decision from this pass:**

7. General document ingestion remains out of scope; the current endpoint intentionally accepts only strict OWD Markdown.

---

## 9. Instructions for Any AI Assistant Working on This Project

- **Do not assume the original `PROJECT_CONTEXT.md` describes the current
  system.** Use this document (§1–§7) as ground truth for what exists
  today. Use the original only for understanding long-term product vision
  and features that are legitimately still "future."
- **Do not re-introduce a second ingestion path.** There is exactly one
  upload → compile → persist path now (`knowledge_studio.py` →
  `OWDCompilerPipeline` → `loader.py` → `KNOWLEDGE_STUDIO.*`). If a new
  ingestion method is ever needed (e.g., real PDF/OCR support), it should
  replace or extend this path, not run alongside it.
- **Do not add mock-data fallbacks "for dev convenience."** That exact
  pattern caused the majority of the bugs found in the recent audit. If
  Snowflake is unreachable, the correct behavior is to raise a real error,
  not silently substitute fake data.
- **Before adding voice, multilingual, TTS, or Knowledge Graph features,**
  confirm with the product owner whether these are actually in scope now —
  per §8 these are still officially undecided, and none of the
  groundwork for them exists yet (no audio handling, no translation layer,
  no cross-document graph store).
- **If you regenerate this document,** merge new source material into it
  rather than hand-patching — same rule the original doc specified for
  itself.

---

*This document reconciles the original product vision
(`PROJECT_CONTEXT.md`) with the actual as-built system as of the most
recent architectural audit and fix pass. Regenerate, don't hand-edit into
drift, when major new source material (a real PRD, finalized DB schema, or
a decision on §8's pending items) becomes available.*
