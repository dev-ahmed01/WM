"""Durable PostgreSQL refresh token control and distributed login throttling.

Refresh tokens never appear in DB: only an HMAC of their unguessable jti.
All state transitions use PostgreSQL atomic updates, safe across replicas.
"""
from __future__ import annotations

import hashlib
import hmac
import ipaddress
from datetime import datetime, timezone
from typing import Any

from app.core.config import settings
from app.core.database import get_postgres_connection


def digest_key(value: str) -> str:
    return hmac.new(
        settings.JWT_SECRET.encode("utf-8"),
        value.encode("utf-8"), hashlib.sha256
    ).hexdigest()


class SessionSecurityRepository:
    @staticmethod
    def record_refresh(jti: str, user_id: str, expires_at: datetime) -> None:
        with get_postgres_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO security.refresh_sessions
                       (jti_hash,user_id,expires_at) VALUES (%s,%s,%s)""",
                    (digest_key(jti), user_id, expires_at),
                )

    @staticmethod
    def is_refresh_valid(jti: str, user_id: str) -> bool:
        with get_postgres_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT EXISTS (
                         SELECT 1 FROM security.refresh_sessions
                         WHERE jti_hash=%s AND user_id=%s
                           AND revoked_at IS NULL AND expires_at > CURRENT_TIMESTAMP
                       )""",
                    (digest_key(jti), user_id),
                )
                return bool(cur.fetchone()[0])

    @staticmethod
    def revoke_refresh(jti: str, user_id: str) -> bool:
        with get_postgres_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """UPDATE security.refresh_sessions SET revoked_at=CURRENT_TIMESTAMP
                       WHERE jti_hash=%s AND user_id=%s AND revoked_at IS NULL""",
                    (digest_key(jti), user_id),
                )
                return cur.rowcount == 1

    @staticmethod
    def revoke_all(user_id: str) -> int:
        with get_postgres_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """UPDATE security.refresh_sessions SET revoked_at=CURRENT_TIMESTAMP
                       WHERE user_id=%s AND revoked_at IS NULL""", (user_id,),
                )
                return cur.rowcount

    @staticmethod
    def rotate_refresh(old_jti: str, new_jti: str, user_id: str,
                       expires_at: datetime) -> bool:
        old_hash, new_hash = digest_key(old_jti), digest_key(new_jti)
        with get_postgres_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("BEGIN")
                try:
                    cur.execute(
                        """UPDATE security.refresh_sessions
                           SET revoked_at=CURRENT_TIMESTAMP, rotated_to_hash=%s
                           WHERE jti_hash=%s AND user_id=%s AND revoked_at IS NULL
                             AND expires_at>CURRENT_TIMESTAMP""",
                        (new_hash, old_hash, user_id),
                    )
                    if cur.rowcount != 1:
                        cur.execute("ROLLBACK")
                        return False
                    cur.execute(
                        """INSERT INTO security.refresh_sessions
                           (jti_hash,user_id,expires_at) VALUES (%s,%s,%s)""",
                        (new_hash, user_id, expires_at),
                    )
                    cur.execute("COMMIT")
                    return True
                except Exception:
                    cur.execute("ROLLBACK")
                    raise


class AuthThrottleRepository:
    @staticmethod
    def consume(action: str, identifier: str, client_ip: str) -> bool:
        # Two independent buckets stop attempts distributed over usernames
        # and repeated attempts against one identity from many IPs.
        try:
            address = str(ipaddress.ip_address(client_ip))
        except ValueError:
            address = "unresolved"
        keys = [digest_key("account|" + action + "|" + identifier.strip().casefold())]
        if settings.AUTH_RATE_IP_BUCKET_ENABLED:
            keys.append(digest_key("ip|" + action + "|" + address))
        decisions = []
        for key in keys:
            with get_postgres_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """INSERT INTO security.auth_rate_windows
                           (key_hash, action, window_started, attempts)
                           VALUES (%s,%s,CURRENT_TIMESTAMP,1)
                           ON CONFLICT (key_hash,action) DO UPDATE
                           SET attempts = CASE
                                 WHEN security.auth_rate_windows.window_started <
                                      CURRENT_TIMESTAMP - (%s * INTERVAL '1 second')
                                 THEN 1 ELSE security.auth_rate_windows.attempts + 1 END,
                               window_started = CASE
                                 WHEN security.auth_rate_windows.window_started <
                                      CURRENT_TIMESTAMP - (%s * INTERVAL '1 second')
                                 THEN CURRENT_TIMESTAMP
                                 ELSE security.auth_rate_windows.window_started END
                           RETURNING attempts""",
                        (key, action, settings.AUTH_RATE_WINDOW_SECONDS,
                         settings.AUTH_RATE_WINDOW_SECONDS),
                    )
                    decisions.append(int(cur.fetchone()[0]) <= settings.AUTH_RATE_MAX_ATTEMPTS)
        return all(decisions)
