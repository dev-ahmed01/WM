"""Unit tests for backend/app/core/security.py security primitives."""

import pytest
from datetime import timedelta
import os

# Set dummy env vars for config settings if missing
os.environ.setdefault("SNOWFLAKE_ACCOUNT", "test_acc")
os.environ.setdefault("SNOWFLAKE_USER", "test_user")
os.environ.setdefault("SNOWFLAKE_PASSWORD", "test_pass")
os.environ.setdefault("SNOWFLAKE_WAREHOUSE", "test_wh")
os.environ.setdefault("SNOWFLAKE_DATABASE", "test_db")
os.environ.setdefault("JWT_SECRET", "super_secret_test_key_1234567890_abcdef")
os.environ.setdefault("N8N_WEBHOOK_BASE_URL", "http://localhost:5678")

from app.core.security import (
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
    decode_token,
)
from app.exceptions import TokenExpiredError, TokenInvalidError


def test_password_hashing():
    raw_password = "SecurePassword123!"
    hashed = hash_password(raw_password)
    assert hashed != raw_password
    assert verify_password(raw_password, hashed) is True
    assert verify_password("WrongPassword", hashed) is False


def test_create_and_decode_access_token():
    user_id = "usr_1001"
    role = "employee"
    department_id = "dept_eng"

    token = create_access_token(user_id=user_id, role=role, department_id=department_id)
    claims = decode_token(token)

    assert claims["sub"] == user_id
    assert claims["role"] == role
    assert claims["department_id"] == department_id
    assert claims["type"] == "access"


def test_create_and_decode_refresh_token():
    user_id = "usr_1001"

    token = create_refresh_token(user_id=user_id)
    claims = decode_token(token)

    assert claims["sub"] == user_id
    assert claims["type"] == "refresh"


def test_decode_expired_token():
    token = create_access_token(
        user_id="usr_1002",
        role="admin",
        department_id="dept_it",
        expires_delta=timedelta(seconds=-10),
    )
    with pytest.raises(TokenExpiredError):
        decode_token(token)


def test_decode_invalid_token():
    invalid_token = "invalid.jwt.token"
    with pytest.raises(TokenInvalidError):
        decode_token(invalid_token)
