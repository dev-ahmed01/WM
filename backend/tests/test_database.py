"""Unit tests for Snowflake database connection layer."""

from unittest.mock import patch, MagicMock
from app.core.database import create_snowflake_connection, get_snowflake_connection, get_db, ping, ping_snowflake_connection


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
