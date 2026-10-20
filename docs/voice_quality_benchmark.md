# WorkMate voice quality — real audio acceptance protocol

## What Phase 7 changes

The standard **Copilot microphone** now calls `POST /api/v1/copilot/voice/transcribe`. This authenticated endpoint returns only the speech transcript, suggested English text, detected language, model-estimated confidence and processing times. It creates **no conversation messages, voice records, analytics events, SOP session or workflow transitions**. It removes its temporary recording after the request. The user edits the draft and presses Send in the standard Copilot text flow. The separate legacy `POST /copilot/voice` flow is retained for API compatibility and retains its explicit-action safety checks, but is not used by the web microphone.

Auto language detection handles English, Hindi and mixed speech, with a Devanagari hint when Whisper reports English despite meaningful Hindi script. Explicit language selections remain en/hi; `hinglish` is an evaluation subgroup, not an unsupported ASR language code. During Auto, Whisper no longer receives a Hindi-only initial prompt. Every transcript is a suggestion—not a validated operational fact, verified quantity, or proof that a step was done.

## Collecting a legitimate holdout

We need **actual independently labeled recordings** from consenting adult testers, not voice synthesized from the same model or text-only examples. Keep originals and manually verified gold transcripts outside Git and GitHub Actions. Collect at least 30 clips each for English, Hindi, and Hinglish, ideally spanning operators, ordinary background noise, short commands, longer questions, numbers, negation, place names, equipment codes, and local accents. Do not collect employee names or confidential SOP material without consent. Record whether microphone language was forced or Auto, hardware/noise, sample rate, and actual audio length. Add parallel human review for disagreements.

The label file is an array located next to private audio files:

```json
[
  {
    "id": "hi-real-001",
    "language": "hi",
    "reference": "पैकेज की सील की जांच करें",
    "audio": "samples/hi-real-001.wav"
  },
  {
    "id": "mix-real-001",
    "language": "hinglish",
    "reference": "Carton को quarantine करो",
    "audio": "samples/mix-real-001.wav"
  }
]
```

**DO NOT COMMIT THE AUDIO OR HOLDOUT LABELS.** The script refuses out-of-directory audio paths, missing clips, oversized recordings and stale predictions. The benchmark never writes source text, labels or transcripts to its report.

```bash
PYTHONPATH=backend python backend/evals/voice_quality.py \
  --manifest /private/workmate_holdout/manifest.json --transcribe \
  --output /private/workmate_holdout/aggregate.json
```

The local Faster-Whisper installation and downloadable model must be available. On a resource-constrained machine, each transcription can be slow; the benchmark reports inference latency in milliseconds. Use the same model, hardware and configuration as the intended production deployment. Confirm that prompts and hotword settings are identical, and report model SHA/revision and recording provenance separately.

## Measured quantities

**WER** is (substitutions + deletions + insertions) / reference word count. **CER (Indic-aware approximated grapheme clusters)** uses the same edit calculation on base characters together with their Unicode marks. Track each across **en**, **hi**, and **hinglish**, plus total and group-specific counts, false command mentions, missed command mentions, language detection accuracy when meaningful, and p50/p95 transcription latency.

Text-only fixture `backend/evals/fixtures/voice_metric_sanity.json` tests benchmark arithmetic and multilingual normalization in CI. It is **not** a speech dataset and its scores must never be described as real STT accuracy.

A preliminary internal deployment should gate on **zero unconfirmed workflow actions**, appropriate handling of all dangerous command/negation cases, no cross-user transcript leakage, a human-reviewed gold sample, reproducible error breakdown, and good-enough latency on the actual target machine. No particular English/Hindi/Hinglish accuracy, production WER or CER is claimed by this phase.

## Remaining release checks

- Independent genuine audio annotation and confusion review; real WER/CER numbers pending.
- Browser E2E for transcript editing, action confirmation, microphone permissions, repeat submits and network interruption.
- Recheck voice permissions and data retention under hosted PostgreSQL.
- Evaluate semantic drift introduced by Hindi ↔ English translation with bilingual reviewers; WER alone does not measure procedural correctness.
- Remove deprecated direct audio-to-Copilot action routes once all clients have migrated to explicit confirmation.
