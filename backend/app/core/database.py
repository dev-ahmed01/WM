"""Snowflake connection management and session handling (sole persistence layer)."""

# Assumption: get_db() yields a Snowflake cursor object for route handler dependency injection and automatically closes the cursor upon route completion.

import contextlib
import logging
from typing import Generator, Any
import snowflake.connector
from app.core.config import settings

logger = logging.getLogger("workmate.database")


def create_snowflake_connection() -> snowflake.connector.SnowflakeConnection:
    """Connection factory creating a new Snowflake connection from settings credentials.

    Passes SNOWFLAKE_ROLE when configured so the connection activates the correct
    role immediately (e.g. SYSADMIN). If SNOWFLAKE_ROLE is empty the parameter is
    omitted and Snowflake uses the user's default role.
    """
    connect_kwargs = dict(
        account=settings.SNOWFLAKE_ACCOUNT,
        user=settings.SNOWFLAKE_USER,
        password=settings.SNOWFLAKE_PASSWORD,
        warehouse=settings.SNOWFLAKE_WAREHOUSE,
        database=settings.SNOWFLAKE_DATABASE,
        schema=settings.SNOWFLAKE_SCHEMA,
        login_timeout=5,
        network_timeout=5,
    )
    if settings.SNOWFLAKE_ROLE:
        connect_kwargs["role"] = settings.SNOWFLAKE_ROLE
    return snowflake.connector.connect(**connect_kwargs)


@contextlib.contextmanager
def get_snowflake_connection() -> Generator[snowflake.connector.SnowflakeConnection, None, None]:
    """Context manager yielding an active Snowflake database connection with reconnect handling."""
    conn: Any = None
    try:
        conn = create_snowflake_connection()
        yield conn
    except Exception as exc:
        if conn is not None:
            try:
                with conn.cursor() as rollback_cursor:
                    rollback_cursor.execute("ROLLBACK")
            except Exception as rollback_exc:
                logger.error("Snowflake rollback failed: %s", rollback_exc)
        logger.warning(f"Snowflake database connection error: {str(exc)}")
        raise
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def get_db() -> Generator[Any, None, None]:
    """FastAPI dependency function yielding a Snowflake cursor for route handlers."""
    with get_snowflake_connection() as conn:
        cursor = conn.cursor()
        try:
            yield cursor
        finally:
            try:
                cursor.close()
            except Exception:
                pass


@contextlib.contextmanager
def get_db_cursor() -> Generator[Any, None, None]:
    """Context manager yielding a Snowflake database cursor."""
    with get_snowflake_connection() as conn:
        with conn.cursor() as cur:
            yield cur


def ping() -> bool:
    """Lightweight check verifying active Snowflake database connectivity by executing 'SELECT 1'."""
    try:
        with get_snowflake_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                return True
    except Exception as exc:
        logger.debug(f"Snowflake ping check failed: {str(exc)}")
        return False


# Alias for backward compatibility with existing health check calls
ping_snowflake_connection = ping
