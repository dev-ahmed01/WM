# Assistant Evaluation (retrieval and safety) — status 2026-11-25

## What was run
`backend/evals/assistant_eval.py` against a local backend with the 85-SOP demo library seeded, **Ollama not running
(`LOCAL_AI_ENABLED=false`)**, so this measures the deterministic catalog/lexical path plus the safety triage — not model
answer quality. Dataset: 293 cases (`backend/evals/fixtures/bilingual_eval_v0.jsonl`): 255 derived from the SOP catalogue
(English title, English purpose, Hindi title), 25 hand-written Hinglish/Hindi/English/misspelling cases, 10
out-of-scope/live-data/injection cases, 3 safety cases. Hardware: developer Windows 11 PC, PostgreSQL 16 in Docker, 1 request at a time.

## Results (raw JSON in `docs/evidence/`)
| Stage | Answerable top-1 | Answerable top-3 | Notes |
|---|---|---|---|
| Baseline (`assistant-eval-baseline-lexical.json`) | 67.5% | 68.9% | Devanagari Hindi questions: **1.2% top-1** (tokenizer was ASCII-only) |
| + Unicode tokenizer + indexed aliases (`…after-aliases.json`) | 97.5% | 99.3% | Authored synonyms/Hinglish phrases were parsed but never indexed or ranked |
| + safety triage (`…with-safety-triage.json`) | 97.5% | 99.3% | 3/3 safety cases produce stop-work + urgent case; 0 wrong workflow starts on 10 unanswerable cases |

Latency (HTTP round-trip, local): p50 ≈ 150 ms, p95 ≈ 470 ms (no model call).

## How to read these numbers — important
- **The derived questions (255 of 293) are circular**: they reuse each SOP's own title/purpose text, so high scores there
  show the pipeline works, not that real workers' questions are answered. They are a regression guard.
- The 25 hand-written cases are a **development set**: the Hinglish aliases added to the catalogue were written after
  seeing failures on similar phrasings. Expect lower scores on unseen real worker language.
- Hand-written Hinglish top-3: 89.5% (2 misses remain: "overtime ke liye kya karna hai", "conveyor ruk gaya").
- Out-of-scope: 3 of 8 still show *suggestions* (never a started workflow). Suggestions with score 0.0 are shown as
  "closest options"; this is weak behaviour for truly unrelated questions and no escalation is created for them yet.
- Not measured at all: answer correctness/groundedness of generated text, citation validity (no citations on the catalog
  path), Hindi speech transcription, language quality, multi-turn follow-ups. The release targets in the brief
  (≥90% grounded-correct, ≥95% citation validity) are therefore **unmet/unmeasured**.

## Known gaps found
1. Out-of-scope questions do not create a "missing knowledge" escalation (Scenario D incomplete).
2. Catalog path does not add citations/version info to answers.
3. Safety triage is rules-based (broad by design; false alarms possible: ~7 of 255 derived SOP-text questions tripped it).
4. Truncated confirmation text bug: "Record each arriving vehicle and confirm it has a. Start it?" (description is cut at a stop-word) — not yet fixed.
5. No Ollama models installed on this machine; embedding/LLM paths, Hindi translation and speech were not exercised.


## Update: knowledge-gap escalation, live-data guard, Ollama enabled (same day)
- Out-of-scope questions with no resembling SOP now say "I don't have an approved procedure for that, so I won't guess" and
  open an escalation (visible in the scoped `/escalations` list): 5 of 8 out-of-scope eval cases escalate; 3 still get
  weak "closest option" suggestions because they share a common word with some SOP. Not yet "fixed".
- "Stock level / bin / shipment status" questions get an explicit "I can't see live warehouse data" reply (no numbers).
- The confirmation-text truncation bug is fixed (full short description; punctuation kept).
- Models installed: `qwen2.5:3b` (1.9 GB) and `nomic-embed-text` (274 MB). `/health/ai` reports both ready.
  Eval with Ollama enabled (`assistant-eval-with-ollama.json`): top-3 98.9%, identical in practice, because the
  SOP-selection stage is deterministic and does not call the model. **The model is only used for free-form follow-ups.**
- Measured on this CPU-only PC: a free-form follow-up question during a workflow ("what if the WMS rejects the receipt?")
  takes **~10 s** and falls back to "I could not find verified organizational guidance" + escalation, although the SOP
  contains that exception. Two causes to fix next: the 8 s `LOCAL_AI_TIMEOUT_SECONDS` is being hit on this hardware,
  and exception/decision text is not part of the evidence for the current step. Deterministic step guidance
  ("yes", "done", next step) responds in ~0.1-0.2 s.
- Full backend suite with live Postgres tests: 581 passed, 1 skipped, 0 failed.


## Final English-only build (same day, after removing voice/Hindi)
Scope decision: **English only**. The Hindi/Hinglish voice, speech and translation stack was deleted (not parked);
Hinglish/Devanagari *text* aliases and the safety triage's Hindi wording for Devanagari input remain because they cost
nothing and help safety. No language model is needed for any number below (`LOCAL_AI_ENABLED=false`).

| Check | Result | Evidence |
|---|---|---|
| SOP lookup, answerable questions (293-case set, English + hand-written Hinglish/Hindi) | top-1 97.5%, top-3 99.3% | `docs/evidence/assistant-eval-english-final.json` |
| English hand-written + typo cases | 100% top-3 | same |
| Out-of-scope / injection (9 cases) | all 9 answered "no approved SOP, won't guess" and opened one knowledge-gap case; 0 workflows started | same |
| Live-data question | explicit "I can't see live warehouse data", no number | same |
| Safety (3 hazard reports) | 3/3 stop-work + urgent case, no repair steps | same |
| In-workflow "what if <exception>?" (85 SOPs) | **78/85 (91.8%)** reuse the SOP's own recovery wording, cited, no escalation | `docs/evidence/followup-eval-final.json` |
| Latency (HTTP, local, no model) | lookup p50 127 ms / p95 451 ms; follow-up p50 58 ms / p95 109 ms | same |

The 7 follow-up misses: 4 are safety-critical SOPs whose exception text ("leaking", "fire") correctly triggers the
safety stop instead of an SOP answer (desired behaviour, counted as a miss by the metric); 3 are ambiguous SOP titles
("picking/packing completion") where WorkMate asks which SOP you mean instead of starting one.

Caveats unchanged: derived questions are circular; the hand-written set was used while tuning; follow-up questions are
derived from SOP text. Answer *quality* on genuinely novel free-form questions needs the language model and a human-graded set.
The `qwen2.5:3b` model is installed but not used by these paths; its measured ~10 s follow-up latency on this 8 GB CPU
machine is the reason the follow-up path was made deterministic.

Housekeeping: evaluation runs write conversations and knowledge-gap rows into the target database. Run them against a
dev/demo database and clear the noise afterwards (`docs/implementation-tracker.md`).
