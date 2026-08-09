"""Free/self-hosted Ollama adapter for embeddings and grounded chat."""

import math
from typing import Any, Dict, List

import httpx

from app.core.config import settings


class LocalAIClient:
    """Small Ollama HTTP client with no managed-cloud fallback."""

    @staticmethod
    def _url(path: str) -> str:
        return f"{settings.LOCAL_AI_BASE_URL.rstrip('/')}{path}"

    @staticmethod
    async def _request_json(method: str, path: str, **kwargs: Any) -> Dict[str, Any]:
        timeout = httpx.Timeout(settings.LOCAL_AI_TIMEOUT_SECONDS)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.request(method, LocalAIClient._url(path), **kwargs)
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                raise ValueError("Local AI provider returned a non-object response")
            return payload

    @staticmethod
    async def health() -> Dict[str, Any]:
        """Return provider reachability without raising into the API health route."""
        if not settings.LOCAL_AI_ENABLED:
            return {"enabled": False, "reachable": False, "models": []}
        try:
            payload = await LocalAIClient._request_json("GET", "/api/tags")
            models = [
                str(item.get("name", ""))
                for item in payload.get("models", [])
                if isinstance(item, dict) and item.get("name")
            ]
            return {"enabled": True, "reachable": True, "models": models}
        except Exception as exc:
            return {
                "enabled": True,
                "reachable": False,
                "models": [],
                "error": type(exc).__name__,
            }

    @staticmethod
    async def embed(texts: List[str]) -> List[List[float]]:
        """Embed a batch through Ollama's local API."""
        if not texts:
            return []
        payload = await LocalAIClient._request_json(
            "POST",
            "/api/embed",
            json={"model": settings.LOCAL_EMBEDDING_MODEL, "input": texts},
        )
        embeddings = payload.get("embeddings")
        if not isinstance(embeddings, list) or len(embeddings) != len(texts):
            raise ValueError("Local embedding provider returned an invalid batch")
        return [[float(value) for value in vector] for vector in embeddings]

    @staticmethod
    async def generate(prompt: str) -> str:
        """Generate a grounded answer through a local Ollama chat model."""
        payload = await LocalAIClient._request_json(
            "POST",
            "/api/chat",
            json={
                "model": settings.LOCAL_CHAT_MODEL,
                "stream": False,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "You are a grounded operational assistant. Follow only the supplied "
                            "verified evidence and never invent procedures or permissions."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                "options": {"temperature": 0},
            },
        )
        message = payload.get("message", {})
        content = message.get("content") if isinstance(message, dict) else None
        if not content or not str(content).strip():
            raise ValueError("Local chat provider returned an empty answer")
        return str(content).strip()

    @staticmethod
    def cosine_similarity(left: List[float], right: List[float]) -> float:
        """Compute cosine similarity without a numeric-library dependency."""
        if not left or len(left) != len(right):
            return 0.0
        left_norm = math.sqrt(sum(value * value for value in left))
        right_norm = math.sqrt(sum(value * value for value in right))
        if left_norm == 0.0 or right_norm == 0.0:
            return 0.0
        return sum(a * b for a, b in zip(left, right)) / (left_norm * right_norm)
