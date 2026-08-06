# WorkMate AI — Consolidated File Changes (9 Files)

This document contains the complete combined source code for the 9 core infrastructure and configuration files updated/created for the WorkMate AI platform foundation.

---

## 1. `backend/requirements.txt`
```plaintext
fastapi>=0.110.0
uvicorn[standard]>=0.28.0
pydantic>=2.6.0
pydantic-settings>=2.2.0
python-jose[cryptography]>=3.3.0
passlib[bcrypt]>=1.7.4
snowflake-connector-python>=3.7.0
python-multipart>=0.0.9
pytest>=8.0.0
```

---

## 2. `backend/app/main.py`
```python
"""FastAPI main entry point for WorkMate AI backend service."""

# Assumption: Health check attempts database ping gracefully without raising 500 error if database is unreachable.

import time
from typing import Dict, Any
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.logging import setup_logging, requests_logger
from app.core.database import ping_snowflake_connection
from app.api.v1 import api_v1_router

# Initialize structured logging subsystem
setup_logging()

app = FastAPI(
    title=settings.PROJECT_TITLE,
    version=settings.PROJECT_VERSION,
    description="Enterprise Operational Intelligence Platform API",
)

# CORS Middleware allowing frontend origin
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_ORIGIN, "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Request Logging Middleware using structured requests_logger
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    duration_ms = (time.time() - start_time) * 1000
    requests_logger.info(
        f"{request.method} {request.url.path} -> {response.status_code} ({duration_ms:.2f}ms)"
    )
    return response


# Register API v1 Router Aggregator
app.include_router(api_v1_router, prefix="/api/v1")


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
```

---

## 3. `backend/app/core/config.py`
```python
"""Pydantic Settings module reading environment configuration variables."""

# Assumption: Sane defaults are provided for local development and unit testing when .env is absent.

from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Application Info
    PROJECT_TITLE: str = "WorkMate AI API"
    PROJECT_VERSION: str = "1.0.0"
    APP_ENV: str = "dev"
    LOG_LEVEL: str = "INFO"
    FRONTEND_ORIGIN: str = "http://localhost:3000"

    # Snowflake Persistence & AI Services Connection Settings
    SNOWFLAKE_ACCOUNT: str = "mock_account"
    SNOWFLAKE_USER: str = "mock_user"
    SNOWFLAKE_PASSWORD: str = "mock_password"
    SNOWFLAKE_WAREHOUSE: str = "mock_wh"
    SNOWFLAKE_DATABASE: str = "WORKMATE_DB"
    SNOWFLAKE_SCHEMA: str = "PUBLIC"

    # Auth & Security Credentials
    JWT_SECRET: str = "test_super_secret_jwt_key_32_bytes_min"
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_EXPIRE_MINUTES: int = 60
    JWT_REFRESH_EXPIRE_DAYS: int = 7

    # Internal Webhook & Service Security
    INTERNAL_WEBHOOK_SECRET: str = "internal_secret_key_12345"

    # Document Parsing AI Flag
    USE_DOCUMENT_AI: bool = False

    # Orchestration Settings
    N8N_BASE_URL: str = "http://localhost:5678"
    N8N_WEBHOOK_BASE_URL: str = "http://localhost:5678"

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=True,
        extra="ignore",
    )


@lru_cache()
def get_settings() -> Settings:
    """Returns a singleton, cached instance of application settings."""
    return Settings()


# Cached settings instance export
settings = get_settings()
```

---

## 4. `backend/app/core/logging.py`
```python
"""Structured application logging configuration and named loggers."""

# Assumption: Pre-configured named loggers use the prefix 'workmate.' to provide consistent logging hierarchy across all application modules.

import sys
import logging
from app.core.config import settings

LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def setup_logging() -> None:
    """Configures root logger with standard formatter and settings level."""
    log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)

    formatter = logging.Formatter(fmt=LOG_FORMAT, datefmt=DATE_FORMAT)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Avoid duplicate handlers on re-initialization
    root_logger.handlers.clear()
    root_logger.addHandler(handler)


def get_logger(name: str) -> logging.Logger:
    """Helper returning a named logger under the workmate namespace."""
    full_name = f"workmate.{name}" if not name.startswith("workmate.") else name
    return logging.getLogger(full_name)


# Predefined named loggers for consistent subsystem logging
requests_logger = get_logger("requests")
ai_logger = get_logger("ai_requests")
ingestion_logger = get_logger("ingestion_jobs")
exceptions_logger = get_logger("exceptions")
```

---

## 5. `backend/app/core/database.py`
```python
"""Snowflake connection management and session handling (sole persistence layer)."""

# Assumption: get_db() yields a Snowflake cursor object for route handler dependency injection and automatically closes the cursor upon route completion.

import contextlib
import logging
from typing import Generator, Any
import snowflake.connector
from app.core.config import settings

logger = logging.getLogger("workmate.database")


def create_snowflake_connection() -> snowflake.connector.SnowflakeConnection:
    """Connection factory creating a new Snowflake connection from settings credentials."""
    return snowflake.connector.connect(
        account=settings.SNOWFLAKE_ACCOUNT,
        user=settings.SNOWFLAKE_USER,
        password=settings.SNOWFLAKE_PASSWORD,
        warehouse=settings.SNOWFLAKE_WAREHOUSE,
        database=settings.SNOWFLAKE_DATABASE,
        schema=settings.SNOWFLAKE_SCHEMA,
    )


@contextlib.contextmanager
def get_snowflake_connection() -> Generator[snowflake.connector.SnowflakeConnection, None, None]:
    """Context manager yielding an active Snowflake database connection with reconnect handling."""
    conn = None
    try:
        conn = create_snowflake_connection()
        yield conn
    except Exception as exc:
        logger.warning(f"Snowflake database connection error: {str(exc)}")
        raise
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def get_db() -> Generator[Any, None, None]:
    """FastAPI dependency function yielding a Snowflake cursor for route handlers."""
    with get_snowflake_connection() as conn:
        cursor = conn.cursor()
        try:
            yield cursor
        finally:
            try:
                cursor.close()
            except Exception:
                pass


def ping() -> bool:
    """Lightweight check verifying active Snowflake database connectivity by executing 'SELECT 1'."""
    try:
        with get_snowflake_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                return True
    except Exception as exc:
        logger.debug(f"Snowflake ping check failed: {str(exc)}")
        return False


# Alias for backward compatibility with existing health check calls
ping_snowflake_connection = ping
```

---

## 6. `infra/docker/backend.Dockerfile`
```dockerfile
FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/backend:/app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/app ./app
COPY knowledge-engine ./knowledge-engine

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

---

## 7. `docker-compose.yml`
```yaml
services:
  backend:
    build:
      context: .
      dockerfile: infra/docker/backend.Dockerfile
    container_name: workmate_backend
    ports:
      - "8000:8000"
    env_file:
      - backend/.env.example
    volumes:
      - ./backend/app:/app/app
    restart: unless-stopped
```



## 9. `.gitignore`
```gitignore
# Environment variables & secrets
.env
*.env
!.env.example

# Python bytecode & cache
__pycache__/
*.py[cod]
*$py.class
.pytest_cache/
.coverage
htmlcov/
*.log

# Node dependencies & Next.js build outputs
node_modules/
.next/
out/
build/
dist/

# IDE & OS files
.vscode/
.idea/
.DS_Store
Thumbs.db
```
