"""PostgreSQL-only connection contract and deliberate no-Snowflake fallback."""
from unittest.mock import MagicMock, patch

import pytest

from app.core import database


def test_postgres_connection_uses_pooled_context():
    fake = MagicMock()
    fake.connection.return_value.__enter__.return_value = "pg_connection"
    with patch.object(database, "_get_pool", return_value=fake):
        with database.get_postgres_connection() as conn:
            assert conn == "pg_connection"
        fake.connection.assert_called_once()


def test_legacy_import_alias_is_always_postgres():
    assert database.get_snowflake_connection is database.get_postgres_connection
    assert database.ping_snowflake_connection is database.ping


def test_healthy_database_query_is_exactly_select_one():
    fake_conn = MagicMock()
    fake_cur = MagicMock()
    fake_conn.cursor.return_value.__enter__.return_value = fake_cur
    fake_cur.fetchone.return_value = (1,)
    with patch.object(database, "get_postgres_connection") as context:
        context.return_value.__enter__.return_value = fake_conn
        assert database.ping() is True
    fake_cur.execute.assert_called_once_with("SELECT 1")


def test_failed_postgres_ping_fails_closed():
    with patch.object(database, "get_postgres_connection", side_effect=RuntimeError("down")):
        assert database.ping() is False


def test_pooled_connection_must_be_closed_on_shutdown():
    pool = MagicMock()
    with patch.object(database, "_pool", pool):
        database.close_postgres_pool()
        pool.close.assert_called_once()
