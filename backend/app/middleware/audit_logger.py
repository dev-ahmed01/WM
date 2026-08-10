"""Audit logging middleware recording state-changing API operations to Snowflake."""

import json
import logging
from typing import Callable, Dict, Any

from fastapi import Request, Response
from starlette.concurrency import run_in_threadpool
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.database import get_db_cursor

logger = logging.getLogger("workmate.audit")


def _record_audit_entry_sync(audit_entry: Dict[str, Any]) -> None:
    """Insert against the SHARED.audit_logs schema provisioned by migrations."""
    try:
        with get_db_cursor() as cursor:
            query = """
                INSERT INTO SHARED.audit_logs (
                    ID,
                    USER_ID,
                    ROLE,
                    ACTION,
                    RESOURCE,
                    IP_ADDRESS,
                    STATUS_CODE,
                    CREATED_AT
                ) SELECT
                    UUID_STRING(),
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    CURRENT_TIMESTAMP()
            """
            cursor.execute(
                query,
                (
                    audit_entry["user_id"],
                    audit_entry["role"],
                    audit_entry["action"],
                    audit_entry["resource"],
                    audit_entry["ip_address"],
                    audit_entry["status_code"],
                ),
            )
    except Exception as exc:
        # Log local exception without breaking client response flow
        logger.error(
            "Failed to record audit log entry in Snowflake: %s | Details: %s",
            exc,
            json.dumps(audit_entry),
        )


class AuditLoggingMiddleware(BaseHTTPMiddleware):
    """Middleware writing audit trails to Snowflake AUDIT_LOG for POST, PUT, PATCH, and DELETE operations."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response = await call_next(request)

        # Audit only state-changing operations
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            user_claims = getattr(request.state, "user", {}) or {}
            user_id = getattr(request.state, "user_id", None) or user_claims.get("sub", "ANONYMOUS")
            role = getattr(request.state, "role", None) or user_claims.get("role", "UNKNOWN")

            action = f"{request.method} {request.url.path}"
            resource = request.url.path
            ip_address = request.client.host if request.client else "0.0.0.0"
            status_code = response.status_code

            audit_entry = {
                "user_id": user_id,
                "role": role,
                "action": action,
                "resource": resource,
                "ip_address": ip_address,
                "status_code": status_code,
            }

            # Offload database insertion out of main asyncio thread
            await run_in_threadpool(_record_audit_entry_sync, audit_entry)

        return response
