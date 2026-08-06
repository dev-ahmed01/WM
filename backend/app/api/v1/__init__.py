"""API v1 router initialization and routing registry."""

from fastapi import APIRouter
from app.api.v1.auth import router as auth_router
from app.api.v1.knowledge_studio import router as knowledge_studio_router

from app.api.v1.copilot import router as copilot_router
from app.api.v1.copilot_session import router as copilot_session_router
from app.api.v1.intelligence import router as intelligence_router
from app.api.v1.escalations import router as escalations_router

api_v1_router = APIRouter()
api_v1_router.include_router(auth_router)
api_v1_router.include_router(knowledge_studio_router)

api_v1_router.include_router(copilot_router)
api_v1_router.include_router(copilot_session_router)
api_v1_router.include_router(intelligence_router)
api_v1_router.include_router(escalations_router)

__all__ = [
    "api_v1_router",
    "auth_router",
    "knowledge_studio_router",

    "copilot_router",
    "copilot_session_router",
    "intelligence_router",
    "escalations_router",
]

