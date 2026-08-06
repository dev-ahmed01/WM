"""Unit tests for Auth API v1 endpoints (/login, /refresh, /me)."""

import pytest
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.auth import router as auth_router
from app.core.security import hash_password, create_refresh_token

app = FastAPI()
app.include_router(auth_router, prefix="/api/v1")

client = TestClient(app)

MOCK_USER = {
    "id": "usr_test123",
    "email": "test@workmate.ai",
    "hashed_password": hash_password("Secret123!"),
    "department_id": "dept_eng",
    "role": "employee",
}


@patch("app.repositories.user_repository.UserRepository.get_user_by_email")
def test_login_success(mock_get_by_email):
    mock_get_by_email.return_value = MOCK_USER

    res = client.post(
        "/api/v1/auth/login",
        json={"email": "test@workmate.ai", "password": "Secret123!"},
    )
    assert res.status_code == 200
    data = res.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"
    assert data["user_id"] == "usr_test123"
    assert data["role"] == "employee"
    assert data["department_id"] == "dept_eng"


@patch("app.repositories.user_repository.UserRepository.get_user_by_email")
def test_login_invalid_password(mock_get_by_email):
    mock_get_by_email.return_value = MOCK_USER

    res = client.post(
        "/api/v1/auth/login",
        json={"email": "test@workmate.ai", "password": "WrongPassword!"},
    )
    assert res.status_code == 401
    assert res.json()["detail"]["error_code"] == "AUTH_INVALID"


@patch("app.repositories.user_repository.UserRepository.get_user_by_id")
def test_refresh_token_success(mock_get_by_id):
    mock_get_by_id.return_value = MOCK_USER
    refresh_token_str = create_refresh_token(user_id="usr_test123")

    res = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_token_str},
    )
    assert res.status_code == 200
    data = res.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"


def test_refresh_with_invalid_token():
    res = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": "invalid_token_string"},
    )
    assert res.status_code == 401
    assert res.json()["detail"]["error_code"] == "AUTH_INVALID"


@patch("app.repositories.user_repository.UserRepository.get_user_by_email")
def test_get_me_protected_route(mock_get_by_email):
    mock_get_by_email.return_value = MOCK_USER

    # First login to get a valid access token
    login_res = client.post(
        "/api/v1/auth/login",
        json={"email": "test@workmate.ai", "password": "Secret123!"},
    )
    access_token = login_res.json()["access_token"]

    # Call /me with Bearer token
    me_res = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert me_res.status_code == 200
    me_data = me_res.json()
    assert me_data["user_id"] == "usr_test123"
    assert me_data["role"] == "employee"
    assert me_data["department_id"] == "dept_eng"
