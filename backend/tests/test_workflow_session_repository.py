"""Snowflake SQL contract tests for workflow session persistence."""

from contextlib import contextmanager
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from app.exceptions.custom_exceptions import DatabaseException
from app.repositories.workflow_session_repository import WorkflowSessionRepository


def connection_factory(cursor):
    @contextmanager
    def factory():
        connection = MagicMock()
        connection.cursor.return_value.__enter__.return_value = cursor
        yield connection

    return factory


def test_session_read_uses_fully_qualified_state_schema(monkeypatch):
    cursor = MagicMock()
    now = datetime.now(timezone.utc)
    cursor.fetchone.return_value = (
        "sess_1", "conv_1", "ver_1", "state_1", None, "usr_1",
        "active", {}, now, now, None,
    )
    cursor.description = [(name,) for name in (
        "id", "conversation_id", "workflow_version_id", "current_state_id",
        "previous_state_id", "user_id", "status", "session_context",
        "started_at", "updated_at", "completed_at",
    )]
    monkeypatch.setattr(
        "app.repositories.workflow_session_repository.get_snowflake_connection",
        connection_factory(cursor),
    )

    session = WorkflowSessionRepository.get_by_id("sess_1")

    sql = cursor.execute.call_args.args[0]
    assert "WORKMATE_COPILOT.workflow_sessions" in sql
    assert "current_state_id" in sql
    assert "current_step" not in sql
    assert session["user_id"] == "usr_1"


def test_session_create_persists_required_state_and_owner(monkeypatch):
    cursor = MagicMock()
    monkeypatch.setattr(
        "app.repositories.workflow_session_repository.get_snowflake_connection",
        connection_factory(cursor),
    )
    WorkflowSessionRepository.create("conv_1", "ver_1", "state_1", "usr_1")
    sql, params = cursor.execute.call_args.args
    assert "current_state_id" in sql and "user_id" in sql
    assert params[3:5] == ("state_1", "usr_1")


def test_progress_transaction_commits_step_and_state_together(monkeypatch):
    cursor = MagicMock()
    cursor.rowcount = 1
    monkeypatch.setattr(
        "app.repositories.workflow_session_repository.get_snowflake_connection",
        connection_factory(cursor),
    )
    WorkflowSessionRepository.apply_progress(
        "sess_1", "state_1", datetime.now(timezone.utc), {"decision_option": "OPT_OK"},
        step_id="step_1", next_state_id="state_2",
    )
    statements = [call.args[0].strip() for call in cursor.execute.call_args_list]
    assert statements[0] == "BEGIN"
    assert any("workflow_step_executions" in statement for statement in statements)
    assert any("current_state_id = %s" in statement for statement in statements)
    assert any("updated_at = %s" in statement for statement in statements)
    assert statements[-1] == "COMMIT"


def test_progress_transaction_rolls_back_after_intermediate_failure(monkeypatch):
    cursor = MagicMock()
    statements = []

    def execute(sql, params=None):
        statement = sql.strip()
        statements.append(statement)
        if "UPDATE WORKMATE_COPILOT.workflow_sessions" in statement:
            raise RuntimeError("update failed")

    cursor.execute.side_effect = execute
    monkeypatch.setattr(
        "app.repositories.workflow_session_repository.get_snowflake_connection",
        connection_factory(cursor),
    )
    with pytest.raises(DatabaseException):
        WorkflowSessionRepository.apply_progress(
            "sess_1", "state_1", datetime.now(timezone.utc), {},
            step_id="step_1", next_state_id="state_2"
        )
    assert statements[-1] == "ROLLBACK"


def test_progress_rolls_back_when_optimistic_lock_loses(monkeypatch):
    cursor = MagicMock()
    cursor.rowcount = 0
    monkeypatch.setattr(
        "app.repositories.workflow_session_repository.get_snowflake_connection",
        connection_factory(cursor),
    )

    with pytest.raises(DatabaseException, match="changed concurrently"):
        WorkflowSessionRepository.apply_progress(
            "sess_1", "state_1", datetime.now(timezone.utc), {}, step_id="step_1"
        )

    statements = [call.args[0].strip() for call in cursor.execute.call_args_list]
    assert not any("INSERT INTO WORKMATE_COPILOT.workflow_step_executions" in sql for sql in statements)
    assert statements[-1] == "ROLLBACK"
