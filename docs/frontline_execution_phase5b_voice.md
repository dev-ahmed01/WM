# Phase 5B — in-task English/Hindi/Hinglish speech, confirmed before guidance

## Operator workflow

Inside an assigned worker task, expand **Ask about this task**. Select **Auto · Hinglish**, English, or Hindi, then press **Speak question**. Recording ends on a pause, after 15 seconds, or via **Stop recording**. Faster-Whisper transcribes via the **existing** authenticated `POST /copilot/voice/transcribe`; optional Hindi-to-English translation is returned as a suggestion. The original transcript remains visible, and the suggested question is **editable**.

**Use this question** copies the edited text into the task's question field. Only a second explicit **Ask** calls `POST /work/guidance/{work_id}`. A worker can discard the transcript, correct Hindi/Romanized/Hinglish terms, or type instead. Audio itself never calls `/copilot/voice`, `/copilot/message`, or any task execution endpoint.

The answer inherits the active task's department, actor, published SOP/version/step, source citations, and blocked-work fail-closed behavior from Phase 5A. It is only a read-only recommendation; voice cannot attest a checkpoint, attach evidence, select an outcome, approve corrective work or release an incident hold.

## Failure and concurrency controls

- Recording depends on browser MediaRecorder plus microphone permission; controls fall back to typed questions where unavailable or denied.
- The existing recorder handles silence, max duration, waveform level and cancellation. Cancellation invalidates a pending permission request, so navigation cannot unexpectedly start a microphone.
- Multipart upload preserves the existing cookie/CSRF proxy. The browser limits clips to 24 MiB; backend enforces its configured 25 MiB cap and supported media types and returns clear authorization/type/size errors.
- Task ID, published SOP version, status or current step changes invalidate any in-flight transcript and guidance. Closing the panel cancels recordings and previews. Explicit request serial numbers suppress duplicate/racing submissions.
- Voice choice is English, Hindi, or auto-detect. **There is no standalone Hinglish recognition model.** Mixed Romanized Hindi, accented warehouse words, codes and negation require operator review. Low confidence is a caution, not a guarantee of transcription accuracy.
- No audio transcription or review is saved by the preview endpoint, and no provisional transcript authorizes workflow execution.

## Verification protocol

1. `backend/tests/test_voice_api.py`: existing authentic JWT, multilingual preview, no-write and MIME coverage, extended with oversized/empty recording and dangerous spoken command preview checks.
2. `backend/e2e/browser_smoke.py`: use disposable PostgreSQL task and published SOP through real Next.js / FastAPI service; run a **synthetic MediaRecorder + preview fixture** to exercise upload, preview, review, editable question, explicit confirmation, citations, unchanged task state, and foreign-department denial. This fixture **does not validate actual Whisper audio**.
3. Real frontend build/typecheck, all backend regressions and live PostgreSQL migrations, browser smoke, staging RLS/security must pass on **the exact PR head** before claiming this phase verified.
4. Inspect the saved mobile and task-panel screenshots, including transcript review and cited answer.

## Release limits

Genuine consented field recordings (English, Hindi, Hinglish), human transcript evaluation, WER/CER including Indic graphemes, number/negation safety analysis, equipment-code errors and p50/p95 on target hardware **remain unverified field gates**. Do not claim ASR accuracy, pilot readiness, physical evidence verification, or a production release on simulated fixture success alone. The broader WorkMate release remains **NO_GO** without actual independent site acceptance.
