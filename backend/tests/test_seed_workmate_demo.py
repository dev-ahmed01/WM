"""Guardrails for non-production WorkMate demonstration fixtures."""
import pytest

from scripts.seed_workmate_demo import DEMO_TASKS, DEMO_USERS, validate_demo_environment


@pytest.fixture
def safe_env():
    return {
        "WORKMATE_DEMO_SEED": "1",
        "APP_ENV": "dev",
        "DATABASE_URL": "postgresql://workmate:localpassword@postgres:5432/workmate",
        "WORKMATE_DEMO_PASSWORD": "local-demo-password-2026",
        "WORKMATE_DEMO_DEPARTMENT": "warehouse",
    }


def test_demo_requires_opt_in(safe_env):
    safe_env.pop("WORKMATE_DEMO_SEED")
    with pytest.raises(RuntimeError, match="opt in"):
        validate_demo_environment(safe_env)


@pytest.mark.parametrize("app_env", ["production", "prod", "staging", ""])
def test_demo_rejects_non_local_environment(safe_env, app_env):
    safe_env["APP_ENV"] = app_env
    with pytest.raises(RuntimeError, match="restricted"):
        validate_demo_environment(safe_env)


@pytest.mark.parametrize("dsn", [
    "postgresql://workmate:pass@external-db:5432/workmate",
    "postgresql://workmate:pass@postgres:5432/production",
    "postgresql://admin:pass@localhost:5432/workmate",
    "https://localhost/workmate",
])
def test_demo_rejects_non_local_database(safe_env, dsn):
    safe_env["DATABASE_URL"] = dsn
    with pytest.raises(RuntimeError, match="standard local"):
        validate_demo_environment(safe_env)


def test_demo_requires_nontrivial_password(safe_env):
    safe_env["WORKMATE_DEMO_PASSWORD"] = "short"
    with pytest.raises(RuntimeError, match="at least 16"):
        validate_demo_environment(safe_env)


def test_demo_references_unique_and_never_assume_execution():
    refs = [item[0] for item in DEMO_TASKS]
    assert len(refs) >= 5 and len(refs) == len(set(refs))
    assert all(item[2] in {"receiving", "putaway", "stock_count", "picking", "dispatch", "other"} for item in DEMO_TASKS)
    assert all(item[3] in {"standard", "high"} for item in DEMO_TASKS)
    assert all(item[4] for item in DEMO_TASKS)
    assert len(DEMO_USERS) >= 2
