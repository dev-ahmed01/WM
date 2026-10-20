"""Authentication API v1 endpoints handling login, refresh, and current profile verification."""

# Assumption: Database connection failures raise HTTP 500 while auth credential mismatches raise HTTP 401 with ApiErrorPayload.

from typing import Dict, Any
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status, Request
from starlette.concurrency import run_in_threadpool

from app.core.security import (
    verify_password,
    create_access_token,
    create_refresh_token,
    decode_token,
)
from app.middleware.auth_middleware import get_current_user
from app.repositories.user_repository import UserRepository
from app.repositories.session_security_repository import SessionSecurityRepository, AuthThrottleRepository
from app.core.config import settings
from app.exceptions import TokenExpiredError, TokenInvalidError, WorkMateException
from app.models.user import (
    LoginRequest,
    RefreshTokenRequest,
    TokenResponse,
    RefreshTokenResponse,
    RevokeRefreshRequest,
    UserProfileResponse,
)

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, request: Request) -> TokenResponse:
    """Verifies credentials against PostgreSQL and creates a revocable refresh session."""
    if settings.AUTH_RATE_LIMIT_ENABLED:
        try:
            permitted = await run_in_threadpool(
                AuthThrottleRepository.consume, "login", payload.email,
                request.client.host if request.client else "unresolved",
            )
        except Exception as exc:
            raise HTTPException(503, detail={
                "error_code": "AUTH_RATE_UNAVAILABLE",
                "message": "Authentication controls are temporarily unavailable.",
            }) from exc
        if not permitted:
            raise HTTPException(429, detail={
                "error_code": "AUTH_RATE_LIMITED",
                "message": "Too many sign-in attempts. Try again later.",
            }, headers={"Retry-After": str(settings.AUTH_RATE_WINDOW_SECONDS)})
    try:
        user = await run_in_threadpool(UserRepository.get_user_by_email, payload.email)
    except WorkMateException as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error_code": "DATABASE_ERROR",
                "message": "Authentication service is temporarily unavailable.",
                "details": None,
            },
        ) from exc

    if not user or not verify_password(payload.password, user["hashed_password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error_code": "AUTH_INVALID",
                "message": "Invalid email/username or password.",
                "details": None,
            },
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = create_access_token(
        user_id=user["id"],
        role=user["role"],
        department_id=user["department_id"],
    )
    refresh_token = create_refresh_token(user_id=user["id"])
    if settings.AUTH_SESSION_STORE_ENABLED:
        claims = decode_token(refresh_token)
        try:
            await run_in_threadpool(
                SessionSecurityRepository.record_refresh, claims["jti"], user["id"],
                datetime.fromtimestamp(claims["exp"], timezone.utc),
            )
        except Exception as exc:
            raise HTTPException(503, detail={
                "error_code": "AUTH_SESSION_UNAVAILABLE",
                "message": "Could not establish a secure session.",
            }) from exc

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        user_id=user["id"],
        role=user["role"],
        department_id=user["department_id"],
    )


@router.post("/refresh", response_model=RefreshTokenResponse)
async def refresh_token(payload: RefreshTokenRequest, request: Request) -> RefreshTokenResponse:
    """Exchanges a valid refresh token for a newly issued access token."""
    try:
        claims = decode_token(payload.refresh_token)
    except TokenExpiredError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error_code": "AUTH_EXPIRED",
                "message": "Refresh token has expired. Please log in again.",
                "details": None,
            },
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    except TokenInvalidError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error_code": "AUTH_INVALID",
                "message": "Invalid refresh token.",
                "details": None,
            },
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    if claims.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error_code": "AUTH_INVALID",
                "message": "Provided token is not a refresh token.",
                "details": None,
            },
            headers={"WWW-Authenticate": "Bearer"},
        )

    if settings.AUTH_RATE_LIMIT_ENABLED:
        try:
            allowed = await run_in_threadpool(
                AuthThrottleRepository.consume, "refresh",
                str(claims.get("sub", "unknown")),
                request.client.host if request.client else "unresolved",
            )
        except Exception as exc:
            raise HTTPException(503, detail={
                "error_code": "AUTH_RATE_UNAVAILABLE",
                "message": "Session verification is temporarily unavailable.",
            }) from exc
        if not allowed:
            raise HTTPException(429, detail={
                "error_code": "AUTH_RATE_LIMITED",
                "message": "Too many session refresh attempts.",
            }, headers={"Retry-After": str(settings.AUTH_RATE_WINDOW_SECONDS)})

    user_id = claims.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error_code": "AUTH_INVALID",
                "message": "Refresh token payload missing subject user ID.",
                "details": None,
            },
        )

    try:
        user = await run_in_threadpool(UserRepository.get_user_by_id, user_id)
    except WorkMateException as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error_code": "DATABASE_ERROR",
                "message": "Authentication service is temporarily unavailable.",
                "details": None,
            },
        ) from exc

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error_code": "AUTH_INVALID",
                "message": "User account associated with this token no longer exists.",
                "details": None,
            },
        )

    rotated_refresh = None
    if settings.AUTH_SESSION_STORE_ENABLED:
        jti = claims.get("jti")
        if not isinstance(jti, str) or not jti:
            raise HTTPException(401, detail={
                "error_code": "AUTH_SESSION_REVOKED",
                "message": "Refresh session is no longer valid. Sign in again.",
            })
        rotated_refresh = create_refresh_token(user_id=user["id"])
        next_claims = decode_token(rotated_refresh)
        try:
            allowed = await run_in_threadpool(
                SessionSecurityRepository.rotate_refresh,
                jti, next_claims["jti"], user["id"],
                datetime.fromtimestamp(next_claims["exp"], timezone.utc),
            )
        except Exception as exc:
            raise HTTPException(503, detail={
                "error_code": "AUTH_SESSION_UNAVAILABLE",
                "message": "Could not verify the refresh session.",
            }) from exc
        if not allowed:
            raise HTTPException(401, detail={
                "error_code": "AUTH_SESSION_REVOKED",
                "message": "Refresh session is no longer valid. Sign in again.",
            })

    new_access_token = create_access_token(
        user_id=user["id"],
        role=user["role"],
        department_id=user["department_id"],
    )

    return RefreshTokenResponse(
        access_token=new_access_token,
        refresh_token=rotated_refresh,
        token_type="bearer",
    )


@router.post("/revoke")
async def revoke_refresh(payload: RevokeRefreshRequest) -> Dict[str, bool]:
    """Idempotent sign-out invalidates one refresh chain server-side."""
    if not settings.AUTH_SESSION_STORE_ENABLED:
        return {"revoked": True}
    try:
        claims = decode_token(payload.refresh_token)
    except (TokenInvalidError, TokenExpiredError):
        return {"revoked": True}
    if claims.get("type") != "refresh" or not claims.get("jti"):
        return {"revoked": True}
    try:
        await run_in_threadpool(
            SessionSecurityRepository.revoke_refresh,
            str(claims["jti"]), str(claims["sub"]),
        )
    except Exception as exc:
        raise HTTPException(503, detail={
            "error_code": "AUTH_SESSION_UNAVAILABLE",
            "message": "Could not revoke session. Retry sign-out.",
        }) from exc
    return {"revoked": True}


@router.get("/me", response_model=UserProfileResponse)
async def get_me(current_user: Dict[str, Any] = Depends(get_current_user)) -> UserProfileResponse:
    """Returns the decoded JWT claims and profile identity of the authenticated user."""
    return UserProfileResponse(
        user_id=current_user.get("sub", ""),
        role=current_user.get("role", "employee"),
        department_id=current_user.get("department_id", ""),
        email=current_user.get("email"),
    )
