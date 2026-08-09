#!/usr/bin/env bash
set -euo pipefail

OLLAMA_URL="${LOCAL_AI_BASE_URL:-http://127.0.0.1:11434}"
CHAT_MODEL="${LOCAL_CHAT_MODEL:-qwen2.5:3b}"
EMBED_MODEL="${LOCAL_EMBEDDING_MODEL:-nomic-embed-text}"

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

echo "Local chat and embedding models are installed and responding."
