"""Authentication API v1 endpoints handling login, refresh, and current profile verification."""

# Assumption: Database connection failures raise HTTP 500 while auth credential mismatches raise HTTP 401 with ApiErrorPayload.

from typing import Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status
from starlette.concurrency import run_in_threadpool

from app.core.security import (
    verify_password,
    create_access_token,
    create_refresh_token,
    decode_token,
)
from app.middleware.auth_middleware import get_current_user
from app.repositories.user_repository import UserRepository
from app.exceptions import TokenExpiredError, TokenInvalidError, WorkMateException
from app.models.user import (
    LoginRequest,
    RefreshTokenRequest,
    TokenResponse,
    RefreshTokenResponse,
    UserProfileResponse,
)

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest) -> TokenResponse:
    """Verifies credentials against users table in Snowflake and returns JWT access + refresh tokens."""
    try:
        user = await run_in_threadpool(UserRepository.get_user_by_email, payload.email)
    except WorkMateException as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error_code": "DATABASE_ERROR",
                "message": f"Failed to execute user authentication query: {exc.message}",
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

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        user_id=user["id"],
        role=user["role"],
        department_id=user["department_id"],
    )


@router.post("/refresh", response_model=RefreshTokenResponse)
async def refresh_token(payload: RefreshTokenRequest) -> RefreshTokenResponse:
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
                "message": f"Invalid refresh token: {exc.message}",
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
                "message": f"Database error during token refresh: {exc.message}",
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

    new_access_token = create_access_token(
        user_id=user["id"],
        role=user["role"],
        department_id=user["department_id"],
    )

    return RefreshTokenResponse(
        access_token=new_access_token,
        token_type="bearer",
    )


@router.get("/me", response_model=UserProfileResponse)
async def get_me(current_user: Dict[str, Any] = Depends(get_current_user)) -> UserProfileResponse:
    """Returns the decoded JWT claims and profile identity of the authenticated user."""
    return UserProfileResponse(
        user_id=current_user.get("sub", ""),
        role=current_user.get("role", "employee"),
        department_id=current_user.get("department_id", ""),
        email=current_user.get("email"),
    )
