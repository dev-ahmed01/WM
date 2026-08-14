# English and Hindi voice

WorkMate's authenticated voice flow is:

`MediaRecorder -> POST /api/v1/copilot/voice -> Faster-Whisper base (tiny fallback) -> M2M100 translation -> grounded Copilot -> M2M100 reverse translation -> text response -> deferred Piper -> protected WAV URL`.

The existing `POST /api/v1/copilot/message` text path is unchanged. Voice requests invoke the same Copilot orchestration, so RBAC, workflow state, citations, validation, and escalation rules remain authoritative.

## Languages

Input and translation are intentionally limited to English (`en`) and Hindi (`hi`) for the current low-memory deployment. Auto Detect remains the frontend default. Faster-Whisper detects the spoken language when the request does not specify one.

Voice capture uses a one-click interaction: select **Speak**, talk naturally, and pause. The browser submits automatically after approximately 1.4 seconds of silence. Selecting **Stop** still submits manually. The composer displays live microphone level and elapsed time so capture cannot fail silently. Recordings with no detected speech stop after eight seconds with an actionable microphone message; individual recordings are forcibly submitted at 15 seconds. Permission denial is surfaced with Chrome-specific recovery guidance. While local transcription, reasoning, translation, and audio generation run, the composer displays an explicit received/processing status.

Translation uses one bidirectional, MIT-licensed `facebook/m2m100_418M` model converted to CTranslate2 INT8 at image build time. It is independent of Ollama, remains resident after first use, and does not evict the Copilot reasoning model. Operational codes, locations, and quantities are validated after translation. Whisper receives configurable bilingual operational vocabulary hints through `WHISPER_HOTWORDS`; these improve noun recognition without defining intents or canned commands.

Piper output is configured independently through `PIPER_VOICE_MAP`. The Docker image installs English `en_US-lessac-medium` and Hindi `hi_IN-pratham-medium`. Voice responses return grounded text first; the frontend requests Piper audio afterward, so synthesis cannot delay the visible answer. Browser speech synthesis is the fallback if local audio generation fails.

## Runtime configuration

The constrained CPU defaults use Faster-Whisper `small`, fall back to `base`, run INT8 with beam size 1, and use four CPU threads so transcription does not starve Copilot reasoning. The 3.67 GB deployment retains one serialized Whisper instance (`VOICE_MODEL_REUSE_MIN_MEMORY_GB=3.5`) instead of reloading it for every recording. Smaller workers use one-at-a-time isolated subprocesses. Docker enables `VOICE_PREWARM_MODELS`, paying Whisper and translation load cost during startup instead of the user's first request. GPU deployments can set `WHISPER_DEVICE=cuda`, select a supported compute type, and enable Piper CUDA when matching runtimes are installed.

Whisper models and generated audio use separate Docker volumes; Piper voices are baked into the backend image. Generated WAV files expire after `VOICE_AUDIO_TTL_SECONDS`; URLs require the same JWT user that created the interaction.

## API

Send multipart form data:

```text
POST /api/v1/copilot/voice
audio=<audio file>
language=auto|en|hi
conversation_id=<optional existing conversation>
synthesize=false
```

The response includes the original transcript, detected language, confidence, English translation, translated Copilot response, latency fields, and the normal Copilot contract. With `synthesize=false`, call `POST /api/v1/copilot/voice/speech` with the response message ID after rendering the text; it returns the authenticated audio URL.

Fetch the returned audio URL with `Authorization: Bearer <JWT>`. Audio is never exposed as a public static file.

## Persistence and analytics

Migration `17_multilingual_voice.sql` creates `WORKMATE_COPILOT.voice_interactions` with original/translated languages and transcripts, response text, confidence, latency, audio ID, and success state. `INTELLIGENCE_HUB.V_ANALYTICS_VOICE_USAGE` reports language usage, voice interaction count, transcription success rate, and average transcription/translation/synthesis latency.

## Operations

Apply migrations and rebuild the backend image after changing voice dependencies or bundled voices:

```bash
PYTHONPATH=.:backend python scripts/deploy_owd_schema.py
docker compose build backend
docker compose up -d backend frontend
```

The first transcription may take longer while Faster-Whisper downloads and warms the selected model. Production images should pre-warm the model volume during deployment when predictable first-request latency is required.
