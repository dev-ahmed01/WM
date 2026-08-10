"""Provider-neutral local AI integrations."""

<<<<<<< HEAD
from app.integrations.ai_gateway import AIGateway
from app.integrations.ai_provider import GeneratedAnswer
from app.integrations.local_ai_provider import OllamaLocalAIProvider

__all__ = ["AIGateway", "GeneratedAnswer", "OllamaLocalAIProvider"]
=======
from app.integrations.cortex_client import CortexClient
from app.integrations.local_ai_client import LocalAIClient

__all__ = ["CortexClient", "LocalAIClient"]
>>>>>>> origin/main
