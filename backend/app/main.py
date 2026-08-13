"""FastAPI main entry point for WorkMate AI backend service."""

# Assumption: Health check attempts database ping gracefully without raising 500 error if database is unreachable.

import time
import logging
import traceback
from contextlib import asynccontextmanager
from typing import Dict, Any
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.logging import setup_logging, requests_logger
from app.core.database import ping_snowflake_connection
from app.middleware.audit_logger import AuditLoggingMiddleware
from app.exceptions import WorkMateException
from app.api.v1 import api_v1_router
from app.integrations.ai_gateway import AIGateway
from app.services.speech_recognition_service import get_speech_recognition_service
from app.services.translation_service import get_translation_service

# Initialize structured logging subsystem
setup_logging()

logger = logging.getLogger("workmate.main")


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Pay reusable local model load cost before accepting voice traffic."""
    if settings.VOICE_ENABLED and settings.VOICE_PREWARM_MODELS:
        started = time.perf_counter()
        logger.info("Prewarming reusable voice models")
        try:
            await get_speech_recognition_service().warm()
            await get_translation_service().warm()
            logger.info("Voice models ready in %.2fs", time.perf_counter() - started)
        except Exception:
            logger.exception("Voice model prewarming failed; continuing startup")
    yield


app = FastAPI(
    title=settings.PROJECT_TITLE,
    version=settings.PROJECT_VERSION,
    description="Enterprise Operational Intelligence Platform API",
    lifespan=lifespan,
)

# Audit Logging Middleware for state-changing endpoints (added first so CORS wraps it)
app.add_middleware(AuditLoggingMiddleware)

# CORS Middleware allowing explicit frontend origins (added LAST so it executes outermost)
configured_origins = [
    origin.strip() for origin in settings.FRONTEND_ORIGIN.split(",") if origin.strip()
]
if settings.APP_ENV.strip().lower() in {"dev", "development", "test"}:
    configured_origins = list(dict.fromkeys([*configured_origins, "http://localhost:3000"]))

app.add_middleware(
    CORSMiddleware,
    allow_origins=configured_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Request Logging Middleware using structured requests_logger
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()
    try:
        response = await call_next(request)
        duration_ms = (time.time() - start_time) * 1000
        requests_logger.info(
            f"{request.method} {request.url.path} -> {response.status_code} ({duration_ms:.2f}ms)"
        )
        return response
    except Exception as exc:
        duration_ms = (time.time() - start_time) * 1000
        requests_logger.error(
            f"Unhandled exception on {request.method} {request.url.path} ({duration_ms:.2f}ms): {exc}\n{traceback.format_exc()}"
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error_code": "INTERNAL_SERVER_ERROR",
                "message": str(exc) if settings.APP_ENV == "dev" else "An unexpected internal server error occurred.",
                "details": None,
            },
        )


@app.exception_handler(WorkMateException)
async def workmate_exception_handler(request: Request, exc: WorkMateException):
    logger.error(f"WorkMateException on {request.method} {request.url.path}: {exc}")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error_code": getattr(exc, "error_code", "WORKMATE_ERROR"),
            "message": getattr(exc, "message", str(exc)),
            "details": getattr(exc, "details", None),
        },
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled Exception on {request.method} {request.url.path}: {exc}\n{traceback.format_exc()}")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error_code": "INTERNAL_SERVER_ERROR",
            "message": str(exc) if settings.APP_ENV == "dev" else "An unexpected server error occurred.",
            "details": None,
        },
    )


# Register API v1 Router Aggregator
app.include_router(api_v1_router, prefix="/api/v1")


# Root Welcome Endpoint
@app.get("/", tags=["Root"])
async def root() -> Dict[str, Any]:
    """Root welcome endpoint providing API service metadata and documentation links."""
    return {
        "name": settings.PROJECT_TITLE,
        "version": settings.PROJECT_VERSION,
        "status": "running",
        "docs_url": "/docs",
        "health_url": "/health",
        "api_v1_prefix": "/api/v1",
    }


# Lightweight Health Check Endpoint
@app.get("/health", tags=["Health"])
async def health_check() -> Dict[str, Any]:
    """Health check endpoint validating system status and database connectivity."""
    db_connected = ping_snowflake_connection()
    return {
        "status": "ok" if db_connected else "degraded",
        "database": "connected" if db_connected else "unreachable",
        "version": settings.PROJECT_VERSION,
    }


@app.get("/health/ai", tags=["Health"])
async def ai_health_check() -> Dict[str, Any]:
    """Report local provider readiness without contacting any managed AI service."""
    local = await AIGateway.health()
    provider_ready = (
        not local["enabled"]
        or (
            local["reachable"]
            and local["chat_ready"]
            and local["embedding_ready"]
        )
    )
    return {
        "status": "ok" if provider_ready else "degraded",
        "provider": "ollama",
        "local": local,
        "chat_model": settings.LOCAL_CHAT_MODEL,
        "embedding_model": settings.LOCAL_EMBEDDING_MODEL,
        "fallback_ready": True,
    }
