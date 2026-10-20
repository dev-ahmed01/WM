"""Deployment security settings and response redaction regression tests."""
import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings, settings
from app.exceptions import WorkMateException
from app.main import app


def test_production_forces_database_credential_revalidation(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "a" * 40)
    monkeypatch.setenv("INTERNAL_WEBHOOK_SECRET", "b" * 30)
    with pytest.raises(ValueError, match="AUTH_REVALIDATE_DB"):
        Settings(
            _env_file=None, APP_ENV="production", AUTH_REVALIDATE_DB=False,
            DATABASE_URL="postgresql://worker:production_secret@postgres.example.org:5432/workmate",
            FRONTEND_ORIGIN="https://workmate.example.org",
        )
    enabled = Settings(
        _env_file=None, APP_ENV="production", AUTH_REVALIDATE_DB=True,
        AUTH_SESSION_STORE_ENABLED=True, AUTH_RATE_LIMIT_ENABLED=True,
        POSTGRES_RLS_REFERENCES=True,
        DATABASE_URL="postgresql://worker:production_secret@postgres.example.org:5432/workmate",
        FRONTEND_ORIGIN="https://workmate.example.org",
    )
    assert enabled.AUTH_REVALIDATE_DB


def test_internal_exception_never_exposes_database_identifiers_in_production(monkeypatch):
    from app.main import workmate_exception_handler
    from starlette.requests import Request
    import asyncio
    monkeypatch.setattr(settings, "APP_ENV", "production")
    request = Request({"type": "http", "method": "POST", "path": "/internal",
                       "headers": [], "query_string": b""})
    exception = WorkMateException(message="postgres://secret-host/internal-sql-password")
    response = asyncio.run(workmate_exception_handler(request, exception))
    assert response.status_code == 500
    assert b"secret-host" not in response.body
    assert b"password" not in response.body


def test_production_refuses_missing_persistent_auth_and_rls_controls(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "a" * 40)
    monkeypatch.setenv("INTERNAL_WEBHOOK_SECRET", "b" * 30)
    with pytest.raises(ValueError, match="AUTH_SESSION_STORE_ENABLED"):
        Settings(_env_file=None, APP_ENV="production", AUTH_REVALIDATE_DB=True,
                 DATABASE_URL="postgresql://worker:prod-secret@db.example.org:5432/workmate",
                 FRONTEND_ORIGIN="https://workmate.example.org")
