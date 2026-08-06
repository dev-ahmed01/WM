"""FastAPI Authentication Dependency Middleware.

Extracts and validates JWT Bearer tokens from the Authorization header,
returning verified user claims or raising ApiErrorPayload HTTP 401 exceptions.
"""

# Assumption: Requests without a valid Bearer token raise HTTP 401 with ApiErrorPayload detail shape.

from typing import Dict, Any, Optional
from fastapi import Depends, Request, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from app.core.security import decode_token
from app.exceptions import TokenExpiredError, TokenInvalidError

security_scheme = HTTPBearer(auto_error=False)


def _build_auth_error(
    status_code: int,
    error_code: str,
    message: str,
    details: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None,
) -> HTTPException:
    """Helper to construct an HTTPException with detail matching ApiErrorPayload shape."""
    return HTTPException(
        status_code=status_code,
        detail={
            "error_code": error_code,
            "message": message,
            "details": details,
        },
        headers=headers,
    )


async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_scheme),
) -> Dict[str, Any]:
    """FastAPI dependency to extract Bearer token, decode claims, and attach user context to request.state.

    Raises:
        HTTPException(401): With error_code "AUTH_INVALID" if token is missing or malformed.
        HTTPException(401): With error_code "AUTH_EXPIRED" if token signature has expired.
    """
    if not credentials or not credentials.credentials:
        raise _build_auth_error(
            status_code=status.HTTP_401_UNAUTHORIZED,
            error_code="AUTH_INVALID",
            message="Missing or invalid authentication credentials.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials

    try:
        claims = decode_token(token)
    except TokenExpiredError as exc:
        raise _build_auth_error(
            status_code=status.HTTP_401_UNAUTHORIZED,
            error_code="AUTH_EXPIRED",
            message=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    except (TokenInvalidError, Exception) as exc:
        raise _build_auth_error(
            status_code=status.HTTP_401_UNAUTHORIZED,
            error_code="AUTH_INVALID",
            message=f"Invalid authentication token: {str(exc)}",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    if claims.get("type") != "access":
        raise _build_auth_error(
            status_code=status.HTTP_401_UNAUTHORIZED,
            error_code="AUTH_INVALID",
            message="An access token is required for this endpoint.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    request.state.user = claims
    request.state.user_id = claims.get("sub", "ANONYMOUS")
    request.state.role = claims.get("role", "UNKNOWN")
    return claims
