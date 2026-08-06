"""Unit tests for Pydantic settings configuration and caching."""

from app.core.config import get_settings, settings


def test_get_settings_cached_instance():
    s1 = get_settings()
    s2 = get_settings()
    assert s1 is s2
    assert s1.PROJECT_TITLE == "WorkMate AI API"


def test_settings_fields_present():
    assert hasattr(settings, "SNOWFLAKE_ACCOUNT")
    assert hasattr(settings, "SNOWFLAKE_USER")
    assert hasattr(settings, "SNOWFLAKE_PASSWORD")
    assert hasattr(settings, "SNOWFLAKE_WAREHOUSE")
    assert hasattr(settings, "SNOWFLAKE_DATABASE")
    assert hasattr(settings, "SNOWFLAKE_SCHEMA")
    assert hasattr(settings, "JWT_SECRET")
    assert hasattr(settings, "JWT_ALGORITHM")
    assert hasattr(settings, "JWT_ACCESS_EXPIRE_MINUTES")
    assert hasattr(settings, "JWT_REFRESH_EXPIRE_DAYS")
    assert hasattr(settings, "N8N_WEBHOOK_BASE_URL")
    assert hasattr(settings, "FRONTEND_ORIGIN")
    assert hasattr(settings, "APP_ENV")
    assert hasattr(settings, "LOG_LEVEL")
