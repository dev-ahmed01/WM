# Multilingual voice

WorkMate's authenticated voice flow is:

`MediaRecorder -> POST /api/v1/copilot/voice -> Faster-Whisper -> Ollama translation -> grounded Copilot -> Ollama reverse translation -> Piper -> protected WAV URL`.

The existing `POST /api/v1/copilot/message` text path is unchanged. Voice requests invoke the same Copilot orchestration, so RBAC, workflow state, citations, validation, and escalation rules remain authoritative.

## Languages

Input and translation are enabled for English (`en`), Hindi (`hi`), Kannada (`kn`), Tamil (`ta`), Telugu (`te`), and Malayalam (`ml`). Auto Detect is the frontend default. Faster-Whisper detects the spoken language when the request does not specify one.

Voice capture uses a one-click interaction: select the microphone, speak naturally, and pause. The browser submits automatically after approximately 1.6 seconds of silence. Selecting the microphone again still stops and submits manually. Recordings with no detected speech stop after 10 seconds with an actionable microphone message; individual recordings are capped at 30 seconds. While local transcription, reasoning, translation, and audio generation run, the composer displays an explicit processing status.

Translation uses the dedicated Ollama `translategemma:4b` model by default through `LOCAL_TRANSLATION_MODEL`; the existing Copilot reasoning model remains independent. The model is configured with `TRANSLATION_KEEP_ALIVE=0` for memory-constrained local Docker deployments and may be retained longer on larger production workers. Operational codes, locations, and quantities are protected from translation and restored exactly. Obvious truncation or identifier loss is retried and then fails safely.

Piper output is configured independently through `PIPER_VOICE_MAP`. The Docker image installs English `en_US-lessac-medium` and Hindi `hi_IN-pratham-medium` immediately. Add regional voices by downloading their `.onnx` and `.onnx.json` files into `PIPER_VOICE_DIR`, then adding a language entry to `PIPER_VOICE_MAP`. Languages without a configured Piper voice still receive translated text; the frontend uses browser speech synthesis when available.

## Runtime configuration

The defaults prefer Faster-Whisper `large-v3` and retry model initialization with `medium`. To prevent worker crash loops, a container whose cgroup or VM memory limit is below `WHISPER_LARGE_MIN_MEMORY_GB` selects `medium` before loading the large model. Workers below `VOICE_MODEL_REUSE_MIN_MEMORY_GB` transcribe in a short-lived subprocess, ensuring native Whisper allocations are returned before Ollama translation begins; larger workers retain the in-process model for lower latency. The isolated worker is bounded by `WHISPER_TRANSCRIPTION_TIMEOUT_SECONDS`. Increase resources or lower these thresholds only after validating peak memory. CPU uses `int8`; GPU deployments can set `WHISPER_DEVICE=cuda`, select a supported compute type, and set `PIPER_USE_CUDA=true` when the matching runtimes are installed.

Whisper models and generated audio use separate Docker volumes; Piper voices are baked into the backend image. Generated WAV files expire after `VOICE_AUDIO_TTL_SECONDS`; URLs require the same JWT user that created the interaction.

## API

Send multipart form data:

```text
POST /api/v1/copilot/voice
audio=<audio file>
language=auto|en|hi|kn|ta|te|ml
conversation_id=<optional existing conversation>
```

The response includes the original transcript, detected language, confidence, English translation, translated Copilot response, latency fields, normal Copilot contract, and an authenticated `audio_url` when Piper has a configured voice.

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
