#!/usr/bin/env bash
set -euo pipefail

<<<<<<< HEAD
MODE="${1:-host}"
=======
>>>>>>> origin/main
OLLAMA_URL="${LOCAL_AI_BASE_URL:-http://127.0.0.1:11434}"
CHAT_MODEL="${LOCAL_CHAT_MODEL:-qwen2.5:3b}"
EMBED_MODEL="${LOCAL_EMBEDDING_MODEL:-nomic-embed-text}"

<<<<<<< HEAD
if [[ "$MODE" == "compose" ]]; then
  docker compose up -d ollama
  docker compose run --rm ollama-model-init
  OLLAMA_URL="http://127.0.0.1:11434"
elif [[ "$MODE" == "host" ]]; then
  if ! command -v ollama >/dev/null 2>&1; then
    echo "ollama is not installed. Install it from the approved package source first." >&2
    exit 1
  fi
  if ! curl --fail --silent --show-error "${OLLAMA_URL%/}/api/tags" >/dev/null; then
    echo "Ollama is not reachable at ${OLLAMA_URL}. Start 'ollama serve' first." >&2
    exit 1
  fi
  ollama pull "$CHAT_MODEL"
  ollama pull "$EMBED_MODEL"
else
  echo "Usage: $0 [host|compose]" >&2
  exit 2
fi

TAGS="$(curl --fail --silent --show-error "${OLLAMA_URL%/}/api/tags")"
python - "$CHAT_MODEL" "$EMBED_MODEL" "$TAGS" <<'PY'
import json, sys
required = sys.argv[1:3]
installed = {item.get("name", "").removesuffix(":latest") for item in json.loads(sys.argv[3]).get("models", [])}
missing = [model for model in required if model not in installed]
if missing:
    raise SystemExit(f"Missing required Ollama models: {', '.join(missing)}")
PY

curl --fail --silent --show-error "${OLLAMA_URL%/}/api/embed" \
  -H 'Content-Type: application/json' \
  -d "{\"model\":\"${EMBED_MODEL}\",\"input\":[\"WorkMate embedding smoke test\"]}" >/dev/null
curl --fail --silent --show-error "${OLLAMA_URL%/}/api/chat" \
  -H 'Content-Type: application/json' \
  -d "{\"model\":\"${CHAT_MODEL}\",\"stream\":false,\"format\":\"json\",\"messages\":[{\"role\":\"user\",\"content\":\"Return {\\\"answer\\\":\\\"OK\\\",\\\"source_ids\\\":[]}\"}]}" >/dev/null
=======
if ! command -v ollama >/dev/null 2>&1; then
  echo "ollama is not installed. Install it from the approved internal package source first." >&2
  exit 1
fi

if ! curl --fail --silent --show-error "${OLLAMA_URL%/}/api/tags" >/dev/null; then
  echo "Ollama is not reachable at ${OLLAMA_URL}. Start 'ollama serve' first." >&2
  exit 1
fi

ollama pull "$CHAT_MODEL"
ollama pull "$EMBED_MODEL"

curl --fail --silent --show-error "${OLLAMA_URL%/}/api/embed" \
  -H 'Content-Type: application/json' \
  -d "{\"model\":\"${EMBED_MODEL}\",\"input\":[\"WorkMate local AI smoke test\"]}" \
  >/dev/null

curl --fail --silent --show-error "${OLLAMA_URL%/}/api/chat" \
  -H 'Content-Type: application/json' \
  -d "{\"model\":\"${CHAT_MODEL}\",\"stream\":false,\"messages\":[{\"role\":\"user\",\"content\":\"Reply with OK\"}]}" \
  >/dev/null
>>>>>>> origin/main

echo "Local chat and embedding models are installed and responding."
