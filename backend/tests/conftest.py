"""Global safeguards keeping the default unit suite hermetic."""

import os

import pytest


# Unit tests never depend on developer or production credentials. These values
# satisfy import-time configuration while all live Snowflake access stays blocked.
os.environ.setdefault("SNOWFLAKE_ACCOUNT", "unit-test-account")
os.environ.setdefault("SNOWFLAKE_USER", "unit-test-user")
os.environ.setdefault("SNOWFLAKE_PASSWORD", "unit-test-password")
os.environ.setdefault("JWT_SECRET", "unit-test-jwt-secret-with-32-characters")
os.environ.setdefault("INTERNAL_WEBHOOK_SECRET", "unit-test-webhook-secret")


def pytest_collection_modifyitems(config, items):
    del config
    if os.getenv("WORKMATE_RUN_LIVE_TESTS") == "1":
        return
    skip = pytest.mark.skip(reason="set WORKMATE_RUN_LIVE_TESTS=1 for live integration tests")
    for item in items:
        if "live_integration" in item.keywords:
            item.add_marker(skip)


@pytest.fixture(autouse=True)
def block_unmocked_snowflake_connections(monkeypatch):
    """Fail immediately if a unit test accidentally reaches live Snowflake."""

    def blocked(*args, **kwargs):
        del args, kwargs
        raise AssertionError("Unit tests must not open live Snowflake connections")

    monkeypatch.setattr("snowflake.connector.connect", blocked)
