"""Unit tests for Pydantic settings configuration and caching."""

from app.core.config import Settings, get_settings, settings


def test_get_settings_cached_instance():
    s1 = get_settings()
    s2 = get_settings()
    assert s1 is s2
    assert s1.PROJECT_TITLE == "WorkMate AI API"


def test_settings_fields_present():
    assert hasattr(settings, "DATABASE_URL")
    assert hasattr(settings, "POSTGRES_RLS_REFERENCES")
    assert hasattr(settings, "AUTH_SESSION_STORE_ENABLED")
    assert hasattr(settings, "JWT_SECRET")
    assert hasattr(settings, "JWT_ALGORITHM")
    assert hasattr(settings, "JWT_ACCESS_EXPIRE_MINUTES")
    assert hasattr(settings, "JWT_REFRESH_EXPIRE_DAYS")
    assert hasattr(settings, "N8N_WEBHOOK_BASE_URL")
    assert hasattr(settings, "FRONTEND_ORIGIN")
    assert hasattr(settings, "APP_ENV")
    assert hasattr(settings, "LOG_LEVEL")


def test_local_ai_is_default_provider():
    defaults = Settings(_env_file=None)

    assert defaults.LOCAL_AI_ENABLED is True


def test_credentials_have_no_checked_in_defaults():
    required = {
         "JWT_SECRET",
        "INTERNAL_WEBHOOK_SECRET",
    }

    assert all(Settings.model_fields[name].is_required() for name in required)
    assert "localhost" in Settings.model_fields["DATABASE_URL"].default
    assert Settings.model_fields["AUTH_SESSION_STORE_ENABLED"].default is False
