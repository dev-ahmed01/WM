"""Snowflake connection management and session handling (sole persistence layer)."""

# Assumption: get_db() yields a Snowflake cursor object for route handler dependency injection and automatically closes the cursor upon route completion.

import contextlib
import logging
from queue import Empty, Full, LifoQueue
from threading import BoundedSemaphore
from typing import Generator, Any
import snowflake.connector
from app.core.config import settings

logger = logging.getLogger("workmate.database")

_POOL_SIZE = max(1, settings.SNOWFLAKE_POOL_SIZE)
_connection_pool: LifoQueue[Any] = LifoQueue(maxsize=_POOL_SIZE)
_pool_slots = BoundedSemaphore(_POOL_SIZE)


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


def _is_closed(conn: Any) -> bool:
    state = getattr(conn, "is_closed", False)
    try:
        return state() is True if callable(state) else state is True
    except Exception:
        return True


def _close_connection(conn: Any) -> None:
    try:
        conn.close()
    except Exception:
        pass


def close_snowflake_pool() -> None:
    """Close all currently idle pooled sessions (primarily shutdown/test cleanup)."""
    while True:
        try:
            _close_connection(_connection_pool.get_nowait())
        except Empty:
            return


@contextlib.contextmanager
def get_snowflake_connection() -> Generator[snowflake.connector.SnowflakeConnection, None, None]:
    """Yield an exclusive pooled Snowflake connection and recycle it on success."""
    conn: Any = None
    failed = False
    acquired = _pool_slots.acquire(timeout=settings.SNOWFLAKE_POOL_ACQUIRE_TIMEOUT_SECONDS)
    if not acquired:
        raise TimeoutError("Timed out waiting for an available Snowflake connection")
    try:
        try:
            conn = _connection_pool.get_nowait()
        except Empty:
            conn = create_snowflake_connection()
        if _is_closed(conn):
            _close_connection(conn)
            conn = create_snowflake_connection()
        yield conn
    except Exception as exc:
        failed = True
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
            if failed or _is_closed(conn):
                _close_connection(conn)
            else:
                try:
                    _connection_pool.put_nowait(conn)
                except Full:
                    _close_connection(conn)
        _pool_slots.release()


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
