# Audio: root cause, repair and evidence

## Why audio "did not work"
The audio feature was not broken so much as **absent**: on the user's instruction (English-only, lower latency) the voice
stack (Whisper transcription, Piper speech, Hindi translation, the recorder hook and every endpoint) had been deleted in
commit `c2ecb19`. The next brief reversed that decision and asked for English **and** Hindi voice, so audio was rebuilt.

Rebuilding it exposed these real failure causes, each found by running the pipeline, not by reading code:

| # | Finding | Evidence | Fix |
|---|---|---|---|
| 1 | The web proxy aborted any backend call after **25 s** (`AbortSignal.timeout(25000)`). A cold Hindi transcription alone took ~25 s on this CPU, so a first recording would be cut off with a generic "backend unavailable". | measured: cold `hi` transcription 25.3 s, warm 8.9 s | `/voice/*` now allowed 120 s (`app/api/backend/[...path]/route.ts`); models are **prewarmed** at API start (`VOICE_PREWARM`) |
| 2 | The installed `av` (v19) is incompatible with `faster-whisper` 1.2.1 (`open() got an unexpected keyword 'metadata_errors'`), which breaks Whisper's own audio decoder. | traceback during the first probe | audio is converted by `ffmpeg` on stdin/stdout to 16 kHz mono PCM and passed as an array; `av` is never used |
| 3 | The Whisper **base** model answered a Hindi recording with an English paraphrase ("Scanner work is not working"), losing the words entirely. | measured on a Piper-generated Hindi sentence | English uses `base` (fast); Hindi/auto use `small` (writes Devanagari) |
| 4 | An English vocabulary hint pushed Hindi output into Latin letters; with no hint the key noun came out as "श्कैनर" / "च्केनर". | A/B on the same fixture | per-language hint **in the language's own script**; "स्कैनर" is now transcribed correctly (asserted in a test) |
| 5 | The local 3B chat model produced unusable Hindi ("cartons" → "cotton zinc"), taking 59 s. | live translate call | replaced with a dedicated translator: M2M100 (MIT licence) via CTranslate2 + a warehouse glossary; ~1–2 s warm. NLLB-200 was rejected: its licence is CC-BY-NC (non-commercial) |
| 6 | Docker Desktop's bind mount failed reading the 1.9 GB translation model (`Out of memory`, `File model.bin is incomplete`). | in-container load error; `cp` failed identically | local trial uses a named volume filled with `docker cp` (checksum verified); servers should mount a normal disk |
| 7 | The spoken Hindi sentence "स्कैनर काम नहीं कर रहा है, मुझे क्या करना चाहिए?" was **refused** ("no approved procedure") while the short form found the SOP: filler words diluted retrieval. | found by the browser test, once its pass condition stopped accepting refusals | `चाहिए…` etc. added to the Hindi stop words; regression test `test_hindi_filler_words.py` |
| 8 | Migration 021 was not applied to the running stack because the `migrate` image is a separate build target and had not been rebuilt (new endpoints returned 500). | 500s in the browser pass | documented: **rebuild all images** (`docker compose build`) before `up` |

Secure-context concern from the brief: `https://localhost` with Caddy's private certificate is still a secure context
(`window.isSecureContext === true`, asserted in the browser test), so `getUserMedia` is available. The only cost of the
untrusted certificate is a click-through warning; for a presentation, import Caddy's root certificate
(`docker compose cp ingress:/data/caddy/pki/authorities/local/root.crt .`, then add it to the Windows
"Trusted Root Certification Authorities" store yourself — this repository does not change the system trust store).
Production HTTPS (a public certificate from Caddy/Let's Encrypt) is unchanged.

## Architecture (all local)
```
mic → MediaRecorder (webm/opus | ogg | mp4) → POST /api/backend/voice/transcribe
    → ffmpeg → 16 kHz PCM → faster-whisper (en: base, hi/auto: small) → text returned to the box (NOT sent, NOT stored)
employee reviews/edits → Send → normal /copilot/message (all grounding, safety and RBAC rules apply)
answer → "Listen": en → Piper en_US-lessac-medium;  hi → M2M100 translation (numbers verified) → Piper hi_IN-pratham-medium
```
Nothing is sent to an external service; audio is processed in memory and never written to disk; every voice route
requires a signed-in user.

## Evidence
| Test | Kind | Result |
|---|---|---|
| `backend/tests/test_voice_pipeline.py` (9 tests) | **Automated fixture**: Piper-generated EN/HI speech → WebM/Opus (what browsers produce) → real HTTP endpoints → Whisper | pass: EN transcript ≥6/9 expected words; HI in Devanagari incl. "स्कैनर"; silence, garbage, empty and oversized uploads give understandable errors; unauthenticated access refused; changed-number translations discarded |
| `backend/e2e/voice_browser_test.js` (EN) | **Automated, real Chromium with a FAKE microphone** fed from `en.wav`: record → upload via proxy → transcribe → send → answer → auto-read-aloud → stop → replay | 12/12 steps pass (before the stricter "must not be a refusal" condition was added; re-run recorded below) |
| `backend/e2e/voice_browser_test.js` (HI) | same with `hi.wav`, Hindi selected | passes: Devanagari transcript, answer, Hindi translate (×3 sentences) + Piper Hindi playback |
| Physical microphone | **NOT tested by me** — no person spoke into a real device | see manual steps |

Latency measured in the Docker stack on an 8 GB CPU laptop (shared with other containers): EN transcription ≈ 2.9 s warm for a
3 s clip; HI ≈ 9 s warm; translation ≈ 1–2 s per answer warm; first call after a restart is slow until prewarm finishes
(~3 min here: Whisper base 17 s, small 31 s, Piper 4 s, translator 125 s). A 16 GB VPS with more CPU should be faster; this
was not measured on one.

## Known limits (be honest with users)
* Hindi **transcription is imperfect** (Whisper small): "मुझें … चाहीं" for "मुझे … चाहिए" in the fixture. Retrieval tolerates
  this because filler words are ignored, but unusual product or place names may be misheard. The employee always sees the
  transcript before sending.
* Hindi **translation is machine-translated** and can still mis-render a domain word; the UI says so and always shows the
  approved English alongside. A translation that changes any number is discarded. Safety stop-work messages are
  pre-authored, not machine-translated.
* **Hinglish** (Hindi in English letters) is typed or spoken as Hindi and matched through authored aliases; accuracy was
  measured earlier on text (see `docs/assistant-evaluation.md`), not on Hinglish *speech*.
* English, Hindi spoken answers use one voice each; no accent options.

## Manual verification still required (needs a person and a real device)
1. Chrome and Edge on Windows: Settings → Privacy → Microphone → allow desktop apps; open the site, tap the mic, allow.
2. Say "How do I post a goods receipt?" → transcript appears in the box, correct it if needed, send; confirm the answer is
   read aloud and the stop button silences it.
3. Switch to हिन्दी, say "स्कैनर काम नहीं कर रहा है"; confirm Devanagari text, a procedure suggestion, and Hindi speech.
4. Deny the microphone once and confirm the message explains how to re-enable it.
5. After recording, confirm the browser's recording indicator disappears (the stream is released).
6. Repeat once on an Android phone (Chrome) and an iPhone (Safari) over HTTPS.
