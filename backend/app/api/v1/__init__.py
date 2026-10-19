"""API v1 router initialization and routing registry."""

from fastapi import APIRouter
from app.api.v1.auth import router as auth_router
from app.api.v1.knowledge_studio import router as knowledge_studio_router
from app.api.v1.reference_knowledge import router as reference_knowledge_router

from app.api.v1.copilot import router as copilot_router
from app.api.v1.copilot_session import router as copilot_session_router
from app.api.v1.intelligence import router as intelligence_router
from app.api.v1.escalations import router as escalations_router
from app.api.v1.pilot import router as pilot_router
from app.api.v1.handover import router as handover_router
from app.api.v1.work_items import router as work_items_router
from app.api.v1.work_execution import router as work_execution_router
from app.api.v1.procedure_drafts import router as procedure_drafts_router

api_v1_router = APIRouter()
api_v1_router.include_router(auth_router)
api_v1_router.include_router(reference_knowledge_router)
api_v1_router.include_router(knowledge_studio_router)

api_v1_router.include_router(copilot_router)
api_v1_router.include_router(copilot_session_router)
api_v1_router.include_router(intelligence_router)
api_v1_router.include_router(escalations_router)
api_v1_router.include_router(pilot_router)
api_v1_router.include_router(handover_router)
api_v1_router.include_router(work_items_router)
api_v1_router.include_router(work_execution_router)
api_v1_router.include_router(procedure_drafts_router)

__all__ = [
    "api_v1_router",
    "auth_router",
    "knowledge_studio_router",
    "reference_knowledge_router",

    "copilot_router",
    "copilot_session_router",
    "intelligence_router",
    "escalations_router",
    "pilot_router",
    "handover_router",
    "work_items_router",
    "work_execution_router",
    "procedure_drafts_router",
]

