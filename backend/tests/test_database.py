"""Unit tests for Snowflake database connection layer."""

from unittest.mock import patch, MagicMock

import pytest

from app.core.database import (
    close_snowflake_pool,
    create_snowflake_connection,
    get_snowflake_connection,
    get_db,
    ping,
    ping_snowflake_connection,
)


@pytest.fixture(autouse=True)
def reset_connection_pool():
    close_snowflake_pool()
    yield
    close_snowflake_pool()


@patch("snowflake.connector.connect")
def test_create_snowflake_connection(mock_connect):
    mock_conn = MagicMock()
    mock_connect.return_value = mock_conn

    conn = create_snowflake_connection()
    assert conn is mock_conn
    mock_connect.assert_called_once()


@patch("app.core.database.create_snowflake_connection")
def test_get_snowflake_connection_context_manager(mock_factory):
    mock_conn = MagicMock()
    mock_factory.return_value = mock_conn

    with get_snowflake_connection() as conn:
        assert conn is mock_conn
    mock_conn.close.assert_not_called()
    close_snowflake_pool()
    mock_conn.close.assert_called_once()


@patch("app.core.database.create_snowflake_connection")
def test_successful_contexts_reuse_connection(mock_factory):
    mock_conn = MagicMock()
    mock_factory.return_value = mock_conn

    with get_snowflake_connection() as first:
        assert first is mock_conn
    with get_snowflake_connection() as second:
        assert second is mock_conn

    mock_factory.assert_called_once_with()


@patch("app.core.database.create_snowflake_connection")
def test_failed_context_discards_connection(mock_factory):
    mock_conn = MagicMock()
    mock_factory.return_value = mock_conn

    with pytest.raises(RuntimeError, match="query failed"):
        with get_snowflake_connection():
            raise RuntimeError("query failed")

    mock_conn.close.assert_called_once()


@patch("app.core.database.get_snowflake_connection")
def test_get_db_generator(mock_get_conn):
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_conn.cursor.return_value = mock_cur
    mock_get_conn.return_value.__enter__.return_value = mock_conn

    gen = get_db()
    cursor = next(gen)
    assert cursor is mock_cur
    try:
        next(gen)
    except StopIteration:
        pass
    mock_cur.close.assert_called_once()


@patch("app.core.database.create_snowflake_connection")
def test_ping_success(mock_factory):
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cur
    mock_factory.return_value = mock_conn

    assert ping() is True
    assert ping_snowflake_connection() is True


@patch("app.core.database.create_snowflake_connection")
def test_ping_failure_graceful(mock_factory):
    mock_factory.side_effect = Exception("Snowflake unreachable")
    assert ping() is False
    assert ping_snowflake_connection() is False
