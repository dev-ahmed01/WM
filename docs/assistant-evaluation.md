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
