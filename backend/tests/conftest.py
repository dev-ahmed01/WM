"""Global safeguards keeping the default unit suite hermetic."""

import os

import pytest


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
