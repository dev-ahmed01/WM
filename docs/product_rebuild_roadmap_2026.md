# WorkMate AI — Product rebuilding roadmap (2026-10-13)

## North star

Turn WorkMate into an operational knowledge and guided-execution product, not a
generic unconstrained chatbot. Employees should get quick, intelligible answers
in English, Hindi, or Hinglish, with **visible source evidence** and workflow
state that only changes on valid actions. Administrators can bring diverse
sources into one governed knowledge workspace. Managers can see where work gets
stuck and what knowledge needs improvement.

**Preserve** Snowflake as the sole durable store, deterministic OWD compiler,
department RBAC, publishing/version controls, audit, local/private AI inference,
workflow-state authorization, citations, and the response validation gate.

## Where the repo starts

- Existing Next.js frontend: Copilot chat, persistent workflow rail, history,
  Knowledge Studio, intelligence dashboard, JWT-scoped roles.
- Knowledge publication: only valid OWD Markdown with deterministic graph load.
- Voice: Faster-Whisper English/Hindi, translated guidance and optional speech.
- Answers: local Ollama, department-scoped retrieval, deterministic SQL fallback,
  canonical low-confidence response and citations.
- Existing tests concentrate on workflow contracts, voice, and grounding;
  there is no checked-in GitHub Actions workflow on `main` at the audit date.

## Incremental build plan

| Phase | Scope | Required evidence before merge |
|---|---|---|
| 1. Experience foundation | Unify navigation, typography/spacing, simplify mobile Copilot, clarify status/citation labels, fix Auto voice language switching | Type check + production build + responsive review + accessibility checks |
| 2. Document intake | Extract PDF, DOCX, PPTX, XLSX, TXT, MD, CSV, TSV, JSON, HTML, RTF into an **admin preview**; validate file sizes and risky archive expansion | Format fixtures, malformed inputs, preview never publishes; **started in phase 1 branch** |
| 3. Governed knowledge library | Durable Snowflake source records, original files in scoped Stage, extraction jobs, page/section anchors, review states, version diffs, role-scoped search | Migration review, atomic/rollback tests, cross-department isolation and deletion tests |
| 4. OCR and layout | Scanned PDF, PNG/JPG via private OCR; table/form/layout reading; optional .doc/.odt conversion in isolated workers | Page-level extraction recall, OCR character-error rate, archive sandboxing, no guessed steps |
| 5. Answer quality | Hybrid lexical + embedding search, multilingual normalization, metadata filtering, optional rerank, query reformulation; distinguish *question* vs *execute step* | Held-out questions, citation precision, abstention accuracy, p95 latency and cost benchmarks |
| 6. Voice reliability | Hindi, English, Hinglish code-switch testing, noisy-floor VAD, transcript confirmation for risky actions, accent/noise evaluation, robust Piper/browser output | Bilingual real-audio test set; WER/CER by language; no unintended step advancement |
| 7. Task-focused product UI | Copilot task context, progressive workflow rail, answer/source expandable panels, comfortable touch targets; Knowledge Studio review and version compare; clear empty/error/loading states | Desktop/tablet/mobile browser tests, keyboard focus, contrast/axe checks |
| 8. Operational intelligence | Knowledge gaps, SOP bottlenecks, unresolved escalations, language success and grounding trends; link manager insights to specific verified evidence | Reproducible metrics, alert thresholds, no invented operational KPI |
| 9. Release hardening | RBAC penetration cases, upload quotas, rate limiting, retention/delete, provider failover, config, CI, backups/restore, observability | Full tests, threat model, deployment runbook, live Snowflake smoke; no unverified release claims |

## Import contract and guardrails

Document **preview** and workflow **publication** remain distinct. In the phase-1
branch, `POST /api/v1/knowledge/preview` accepts common formats and returns
a 12,000-character admin-only, in-memory text preview. It does not stage files,
store embeddings, update workflow tables, or make content queryable by Copilot.
Scanned PDF OCR is not yet implemented. The existing OWD `/upload` contract
remains unchanged for backward compatibility.

Next, store extracted source content and page/section provenance in Snowflake.
A reviewer can tag a source as *reference knowledge* (available for grounded Q&A
after approval), or derive an editable **draft OWD** for procedural use. Drafts
must pass deterministic parse/validation, show side-by-side source evidence,
and receive explicit human approval before publication. Never promote arbitrary
prose into executable decisions automatically.

Recommended progressive coverage:

- **Current extraction preview**: MD, TXT, CSV, TSV, JSON, HTML/HTM, RTF, PDF
  with selectable text, DOCX, XLSX, PPTX.
- **Next**: PNG, JPG, TIFF and image-only PDFs through OCR; tables, diagrams,
  and page layout with bounding boxes.
- **Later adapters**: ODT/ODS/ODP, email attachments, older DOC/XLS/PPT, ZIP
  bundles, connectors to organizational file sources, subject to sandboxing.
- Unknown/corrupt/encrypted/unsupported types fail with actionable reasons.
  Do not promise that literally every possible file can be parsed.

## Voice acceptance criteria

- Keep `auto` selected across recordings; one Hindi utterance must not pin all
  subsequent requests to Hindi, or vice versa.
- Always display transcription and detected language; offer edit-and-resubmit
  for low-confidence or mixed-language input before a consequential workflow
  state mutation.
- Compare base vs small/medium Whisper under real warehouse noise; measure
  WER, mixed-script normalization and latency independently.
- Never infer completion of a safety-critical step from vague speech. Re-use
  the validated graph transition/decision gate.

## Answer acceptance criteria

Create a fixed benchmark of authentic receiving, putaway, cycle-count, picking
and shipping questions with paraphrases, typo variants, multilingual inputs,
contradictory documents, missing evidence, and department-denied sources.
Capture **citation precision**, correct step retrieval, state mutation errors,
grounded abstention, multilingual answer usefulness and latency. Do not grade
only how fluent the LLM sounds.

Response presentation: (1) short direct answer, (2) actionable steps if
appropriate, (3) relevant safety caveat, (4) source title/version/step, and
(5) *I couldn't verify this* if evidence is inadequate. Preserve explicit
consultation-versus-execution distinction.

## Product differentiation worth building

1. **Ask or Do**: users can consult future steps without accidentally advancing
   the recorded workflow.
2. **SOP gap detector**: identify repeated questions with weak/conflicting
   sources and request an administrator review.
3. **Shift handover**: structured summaries based on persisted execution events,
   not an invented narrative.
4. **Source-linked escalation**: supervisor sees question, exact SOP version,
   prior verified actions, and why evidence was insufficient.
5. **Multi-language operations mode**: Hindi/English code switching with a
   transparent transcript and the same workflow authority.
6. **Document-to-workflow drafting**: administrative extraction, reviewer edits,
   evidence-backed decision graph, approved publication.
7. **Change impact**: when SOP versions change, surface affected active sessions
   and evaluate transition compatibility before activating a new graph.

## Architecture decisions

- Backend: isolate `document_extraction`, `document_registry` (future),
  `indexing` (future), `retrieval`, `speech`, and `workflow_state` behind
  tests. Break down the current large `api/v1/copilot.py` only with unchanged
  route contracts and complete session regression coverage.
- New Snowflake tables must use ordered `analytics/migrations`; no second DB,
  invisible local vector store persistence, or unsecured external OCR service.
- n8n remains optional orchestration/notification only and **never** decides
  operational instructions.
- UI: calm light surfaces, forest-green actions, a single useful primary action
  per page, expandable secondary metadata, and consistent 14–16px primary text.
- Each phase is a reviewable PR with explicit tests and documented known gaps.

## Phase-1 branch status

Implemented on `feat/workmate-experience-foundation`:

- Updated light workspace navigation and clearer role-aware grouping.
- Mobile Copilot workflow panel collapsed by default, expandable on demand.
- Auto voice language setting stays Auto across recordings.
- Typing while recording discards that partial recording rather than duplicating
  a voice submission.
- Non-publishing document extraction preview API and Knowledge Studio review UI.
- Extraction safety fixtures and documented support limits.

**Not claimed complete:** OCR, document indexing/publication beyond OWD, full UI
redesign for every screen, bilingual acoustic accuracy benchmarking, retrieval
improvements, live Snowflake checks and browser QA.
