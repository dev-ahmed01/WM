# WorkMate — demo guide (local, https://localhost)

## Start / restart
```bash
cd deploy/vps
docker compose -f compose.yml -f compose.local.yml build      # builds ALL images, incl. migrate (migration 021 needs it)
docker compose -f compose.yml -f compose.local.yml up -d
docker compose -f compose.yml -f compose.local.yml restart ingress
```
The speech/translation models live in the Docker volume `workmate_voice` (filled once with `docker cp voice-models/{piper,whisper,m2m100}`).
After a restart the API warms the models for ~3 minutes; ask one English and one Hindi question before presenting.
The Ollama on the host must be running (`ollama list` shows `qwen2.5:3b`, `nomic-embed-text`). Open https://localhost and click
through the certificate warning (or trust Caddy's local root certificate yourself).

## Accounts (local demo only)
| Role | Sign in | Lands on |
|---|---|---|
| Administrator | `Admin` / `admin*123` (set by request; weak, never use outside this laptop) | Knowledge Studio |
| Manager | `demo_manager_hyd@demo.workmate.test` — password in git-ignored `.demo-credentials.local.json` | Overview |
| Employee | `demo_receiving@demo.workmate.test` — same file | Assistant |

## Suggested 6-minute path
1. **Employee**: "How do I post a goods receipt?" → approved steps + sources; tap 👍; tap 🔊 (reads aloud).
2. Switch to **हिन्दी**, tap the microphone, say "स्कैनर काम नहीं कर रहा है" → Devanagari text → Send → procedure options → Listen (Hindi).
3. Ask something not covered ("policy for bonus payments") → honest "no approved procedure", a request is opened. Or tap **Ask a person** under an answer.
4. **Escalations** (employee) shows the request; **History** shows the conversation (rename/archive).
5. **Admin → Conversations**: open it, reply, add an internal note, assign, resolve. **Knowledge Studio**: all 85 SOPs, *Test answer*, *Upload*.
6. **Employee** sees the reply and closes it. **Manager → Overview / Escalations / Analytics** reflect the activity (counts come from recorded events).

## What is verified / not
* Verified: 50 live-database tests (both DB roles), 9 voice pipeline tests, real-Chromium voice test with a fake microphone (EN + HI), 3 roles × 3 pages × 4 widths with no overflow or console errors.
* **Not verified**: a person speaking into a physical microphone; phones; load; a real server deployment. See `docs/voice-audio-report.md`.
* Hindi transcription and translation are machine output and can be wrong; the UI shows the English approved answer alongside.
