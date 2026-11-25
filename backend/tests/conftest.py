"""Global safeguards keeping the default unit suite hermetic."""

import os
import tempfile

import pytest


# Unit tests never depend on developer or production credentials. These values
# satisfy import-time configuration while all live PostgreSQL access stays blocked.
os.environ.setdefault("JWT_SECRET", "unit-test-jwt-secret-with-32-characters")
os.environ.setdefault("INTERNAL_WEBHOOK_SECRET", "unit-test-webhook-secret")
os.environ.setdefault("VOICE_AUDIO_DIR", os.path.join(tempfile.gettempdir(), "workmate_unit_voice"))


def pytest_collection_modifyitems(config, items):
    del config
    if os.getenv("WORKMATE_RUN_LIVE_TESTS") == "1":
        return
    skip = pytest.mark.skip(reason="set WORKMATE_RUN_LIVE_TESTS=1 for live integration tests")
    for item in items:
        if "live_integration" in item.keywords:
            item.add_marker(skip)


@pytest.fixture(autouse=True)
def block_unmocked_postgres_connections(monkeypatch):
    """Fail immediately if a unit test accidentally reaches live Snowflake."""

    def blocked(*args, **kwargs):
        del args, kwargs
        raise AssertionError("Unit tests must not open live PostgreSQL connections")

    if os.getenv("WORKMATE_RUN_LIVE_TESTS") == "1":
        return
    monkeypatch.setattr("psycopg.connect", blocked)


class _EveryDepartment(frozenset):
    """Unit-test scope: every department is allowed (the real lookup needs a database)."""

    def __contains__(self, item):
        return True


@pytest.fixture(autouse=True)
def permissive_department_scope(request, monkeypatch):
    """Mocked-repository unit tests bypass the tenant lookup; live tests use the real one."""
    if "live_integration" in request.keywords:
        return
    monkeypatch.setattr("app.middleware.tenant_scope._load", lambda *_a, **_k: _EveryDepartment())
    # Mocked-repository upload tests exercise the direct-publish branch; the approval gate has live tests.
    from app.core.config import settings
    monkeypatch.setattr(settings, "PUBLISH_REQUIRES_APPROVAL", False)
