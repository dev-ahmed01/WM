"""PostgreSQL connection boundary (single durable WorkMate database).

The old function names are deprecated import aliases only. They do not connect to
Snowflake. New code must use get_postgres_connection and DATABASE_URL.
"""
from __future__ import annotations

import contextlib
import logging
from typing import Any, Generator

from psycopg_pool import ConnectionPool

from app.core.config import settings

logger = logging.getLogger("workmate.database")
_pool: ConnectionPool | None = None


def _get_pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        _pool = ConnectionPool(
            conninfo=settings.DATABASE_URL,
            min_size=0,
            max_size=settings.POSTGRES_POOL_SIZE,
            timeout=settings.POSTGRES_POOL_TIMEOUT_SECONDS,
            kwargs={"autocommit": True},
            open=True,
        )
    return _pool


@contextlib.contextmanager
def get_postgres_connection() -> Generator[Any, None, None]:
    """Provide an exclusive pooled connection; rollback and release on error."""
    with _get_pool().connection() as conn:
        yield conn


def close_postgres_pool() -> None:
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None


def get_db() -> Generator[Any, None, None]:
    with get_postgres_connection() as conn:
        with conn.cursor() as cur:
            yield cur


@contextlib.contextmanager
def get_db_cursor() -> Generator[Any, None, None]:
    with get_postgres_connection() as conn:
        with conn.cursor() as cur:
            yield cur


def ping() -> bool:
    try:
        with get_postgres_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                return cur.fetchone() == (1,)
    except Exception as exc:
        logger.debug("PostgreSQL health probe failed: %s", type(exc).__name__)
        return False


# Temporary API compatibility for repository modules pending SQL migration.
# THESE ALIASES ALWAYS USE POSTGRESQL. They never make Snowflake connections.
get_snowflake_connection = get_postgres_connection
close_snowflake_pool = close_postgres_pool
ping_snowflake_connection = ping
