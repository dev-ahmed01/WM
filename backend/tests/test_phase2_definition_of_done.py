"""Phase 2 Definition of Done (DoD) verification tests."""

import pytest
from datetime import timedelta
from unittest.mock import patch
from fastapi import FastAPI, Depends, status
from fastapi.testclient import TestClient

from app.api.v1.auth import router as auth_router
from app.core.security import hash_password, create_access_token
from app.middleware.auth_middleware import get_current_user
from app.middleware.rbac_middleware import require_role

# Construct FastAPI app for DoD verification
app = FastAPI()
app.include_router(auth_router, prefix="/api/v1")

@app.get("/api/v1/admin-protected", dependencies=[Depends(require_role("admin"))])
async def admin_protected_route():
    return {"status": "success", "message": "Welcome Admin!"}

client = TestClient(app)

# Seeded user fixture
SEEDED_EMPLOYEE = {
    "id": "usr_emp001",
    "email": "employee@workmate.ai",
    "hashed_password": hash_password("Test1234!"),
    "department_id": "dept_eng",
    "role": "employee",
}

SEEDED_ADMIN = {
    "id": "usr_admin001",
    "email": "admin@workmate.ai",
    "hashed_password": hash_password("Test1234!"),
    "department_id": "dept_admin",
    "role": "admin",
}


# 1. POST /auth/login with a seeded user returns a valid access token
@patch("app.repositories.user_repository.UserRepository.get_user_by_email")
def test_dod_1_login_seeded_user_returns_valid_token(mock_get_by_email):
    mock_get_by_email.return_value = SEEDED_EMPLOYEE

    response = client.post(
        "/api/v1/auth/login",
        json={"email": "employee@workmate.ai", "password": "Test1234!"},
    )
    assert response.status_code == 200, f"Expected 200 OK, got {response.status_code}"
    data = response.json()
    assert "access_token" in data, "Response missing access_token"
    assert "refresh_token" in data, "Response missing refresh_token"
    assert data["token_type"] == "bearer"
    assert data["user_id"] == "usr_emp001"


# 2. GET /auth/me with that token returns correct role/department claims
@patch("app.repositories.user_repository.UserRepository.get_user_by_email")
def test_dod_2_get_me_returns_role_and_department_claims(mock_get_by_email):
    mock_get_by_email.return_value = SEEDED_EMPLOYEE

    # Step A: Login to acquire token
    login_res = client.post(
        "/api/v1/auth/login",
        json={"email": "employee@workmate.ai", "password": "Test1234!"},
    )
    access_token = login_res.json()["access_token"]

    # Step B: Call /auth/me with Bearer token
    me_res = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert me_res.status_code == 200
    me_data = me_res.json()
    assert me_data["user_id"] == "usr_emp001"
    assert me_data["role"] == "employee"
    assert me_data["department_id"] == "dept_eng"


# 3. GET /auth/me with no token returns 401 in the correct error shape
def test_dod_3_get_me_no_token_returns_401_error_shape():
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401
    payload = response.json()
    
    # Verify exact ApiErrorPayload shape {error_code, message, details}
    assert "detail" in payload
    error_detail = payload["detail"]
    assert error_detail["error_code"] == "AUTH_INVALID"
    assert "message" in error_detail
    assert "details" in error_detail


# 4. A route protected with require_role("admin") returns 403 for an employee token
@patch("app.repositories.user_repository.UserRepository.get_user_by_email")
def test_dod_4_require_role_admin_returns_403_for_employee_token(mock_get_by_email):
    mock_get_by_email.return_value = SEEDED_EMPLOYEE

    # Acquire employee token
    login_res = client.post(
        "/api/v1/auth/login",
        json={"email": "employee@workmate.ai", "password": "Test1234!"},
    )
    emp_token = login_res.json()["access_token"]

    # Access admin protected route with employee token
    res = client.get(
        "/api/v1/admin-protected",
        headers={"Authorization": f"Bearer {emp_token}"},
    )
    assert res.status_code == 403
    payload = res.json()
    assert payload["detail"]["error_code"] == "AUTH_FORBIDDEN"
    assert "not authorized" in payload["detail"]["message"]


# 5. Token expiry actually expires (tested with short expiry)
def test_dod_5_token_expiry_actually_expires():
    # Issue a token expired in the past (-5 seconds)
    expired_token = create_access_token(
        user_id="usr_emp001",
        role="employee",
        department_id="dept_eng",
        expires_delta=timedelta(seconds=-5),
    )

    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {expired_token}"},
    )
    assert response.status_code == 401
    payload = response.json()
    assert payload["detail"]["error_code"] == "AUTH_EXPIRED"
    assert "expired" in payload["detail"]["message"].lower()
