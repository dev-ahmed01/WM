# WorkMate AI Phase 12 — independent SOP / bilingual evaluation

## Evaluation status, and what the numbers actually mean

The repository has a **real PostgreSQL-backed evaluation harness** plus a tiny **synthetic** data test. An 8-case synthetic CI success establishes only that the benchmark, tenant filtering, citation anchors, and current fallback operate as designed against disposable PostgreSQL. **It does not establish production answer quality.** The existing offline 16-case metric fixture and text-only speech fixture also do not establish real user or microphone accuracy.

Phase 11 intentionally runs without Ollama embeddings or microphone inference. To measure the full AI stack, provision a separate private evaluation environment with the final model version, CPU/GPU capacity, OCR and voice services. Do not change the production reference approval status or gather user recordings merely to fill out benchmarks.

## Required independently reviewed cohort

- At least **120 genuine human-authored warehouse questions**, split across English, Hindi, and Hinglish with at least 30 each and broad coverage of receiving, verify, putaway, cycle count, pick, pack/ship, exceptions and safe refusals. Oversample missing evidence, archived/conflicting revisions, department boundary, numerals, units, PPE and negation. Use questions written by warehouse operators, not queries generated from the same SOP by the model under test.
- Have two qualified independent reviewers verify the expected document ID, quoted supporting text and the proper **abstain** outcome. Resolve disagreements in a recorded adjudication sheet. Include a blind holdout that developers do not tune against. The reviewer signs off on whether the SOP itself is approved and operationally correct; citation existence cannot prove safe policy.
- For **English, Hindi, and Hinglish voice**, obtain consented independently labeled audio (recommended >=30 genuine clips per language). Capture accents, devices, ambient noise, safety-critical commands, numbers, negation and name/code pronunciation. No synthetic/text-only speech fixture can replace field audio.
- Keep raw questions, audio, annotations, reviewer names and answers outside Git, CI logs and reports. Use a private access-restricted directory and remove identifying text from the benchmark export.

### Private SOP-label format

Write the following JSON into a private `/private/workmate_gold.json`, replacing IDs and questions with adjudicated labels for documents that are currently APPROVED in the same PostgreSQL department:

```json
[
  {
    "id": "operator-en-001",
    "language": "en",
    "scenario": "routine",
    "department_id": "receiving",
    "question": "What is the required check before putaway?",
    "expected_document_id": "actual-approved-document-id",
    "expected_evidence": "literal required passage from that document"
  },
  {
    "id": "missing-qa-001",
    "language": "hinglish",
    "scenario": "missing_evidence",
    "department_id": "receiving",
    "question": "What is our undocumented compressor pressure limit?",
    "expected_document_id": null
  }
]
```

A null expected ID requires abstention; positive cases require the correct approved cited document, and `expected_evidence` requires its literal phrase in a validated citation. Empty evidence labels are allowed only for an intentionally coarse document-ID evaluation and are not a substitute for reviewer annotations.

### Run against the current PostgreSQL backend

```bash
export PYTHONPATH=backend
export WORKMATE_EVAL_LIVE=1
# DATABASE_URL points to an isolated read-only evaluation credential with
# permissions for current approved references, not an owner or production writer.
python backend/evals/warehouse_acceptance.py \
  --manifest /private/workmate_gold.json --min-cases 120 \
  --min-per-language 30 --min-negative 20 \
  --fail-on-invalid --output /private/workmate_aggregate.json
```

The script computes current department-scoped retrieval, actual answer validation, and resolves cited chunks directly from PostgreSQL to check approval status and exact offsets. It reports top-1/recall@5, first-citation document match, adjudicated evidence coverage, negative-case abstention, false answers, citation precision, invalid spans and latency p50/p95 by language **and by scenario** (routine, missing evidence, unsafe instruction, cross-department, draft, archived, conflicting revision). Every report also includes the SHA-256 of the private input manifest, flags whether the live local semantic reranker was enabled, and includes an optional `WORKMATE_EVAL_RELEASE_SHA` revision. These metadata identify the evaluation without publishing the raw questions.

**Critical limitations:** this is an extractive answer / citation test, not a benchmark for generative model reasoning, semantic equivalence, procedural safety, hardware performance or a deployed network hop. If Ollama is disabled, results are lexical fallback only; report the actual model/device settings. Direct database evaluation measures API-layer services, not browser-to-server latency. A correctly quoted but obsolete/wrong SOP still needs human rejection. The harness currently reads trusted approved documents from PostgreSQL but does not automatically assess contradictory approved-source revisions.

### Voice metric scoring

When genuine audio is available, use the Phase 7 evaluator with reviewed transcripts and the final Faster-Whisper model:

```bash
PYTHONPATH=backend python backend/evals/voice_quality.py \
  --manifest /private/voice_holdout/manifest.json --transcribe \
  --output /private/voice_holdout/aggregate.json
```

Review English/Hindi/Hinglish WER, grapheme CER, missed/false command words, language detection on the two supported base languages, and p95 inference latency on the intended hardware. A low WER is **not** proof that translation preserved safety instructions. Manually inspect negations, numbers, imperative commands and mistranslated escalation steps. The browser still requires explicit transcript review before a consequential workflow message.

## Release criteria (proposed, require human acceptance)

Before a pilot, prefer: **zero cross-department citations**, **zero unapproved/archived citations**, **zero citation offset mismatches**, **zero automatic voice-driven workflow advances**, a human-reviewed low false-answer/unsafe-action rate on safety-critical queries, documented answer/abstention quality by language, and acceptable p95 latency on the actual deployed system. Tune thresholds from a disclosed frozen holdout and operational severity review, not from this synthetic CI suite.

## Staging verification

The Phase 11 staging stack and the existing GitHub Actions prove local role separation, encrypted backup parsing, and the real Chromium ↔ FastAPI ↔ PostgreSQL document lifecycle. **No public hosted staging URL has been verified.**

After provisioning HTTPS staging, run:

```bash
python scripts/check_staging_https.py --origin https://YOUR_REAL_STAGING_HOST
```

This **read-only** probe checks certificate-backed HTTPS, HTML login, HSTS, nosniff, and a no-store 401 on unauthenticated session introspection. It cannot prove the login, private API/network isolation, backup PITR, voice quality, or role correctness by itself. Follow the Phase 11 runbook for full authenticated manual browser review, hosted backup recovery and offsite evidence.

## Outstanding acceptance steps

1. Acquire and independently annotate the SOP/question/audio holdouts under consent and data handling policies.
2. Confirm managed PostgreSQL and HTTPS staging with a non-owner database role and private network routing; perform an off-host recovery drill.
3. Deploy the final approved Ollama/embedding/Whisper configuration to a private model-capable evaluation environment.
4. Run the held-out evaluation, investigate every invalid or safety-relevant result, freeze model/dataset revisions, obtain reviewer signoff.
5. Only after hosted acceptance and security gates should the cumulative release PR be considered for merging.
