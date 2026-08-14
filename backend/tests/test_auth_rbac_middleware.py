"""Unit tests for auth_middleware and rbac_middleware dependencies."""

from fastapi import FastAPI, Depends
from fastapi.testclient import TestClient

from app.core.security import create_access_token, create_refresh_token
from app.middleware.auth_middleware import get_current_user
from app.middleware.rbac_middleware import require_role, require_own_department
from datetime import timedelta

app = FastAPI()

@app.get("/me")
async def get_me(user: dict = Depends(get_current_user)):
    return user

@app.get("/admin-only")
async def admin_only(user: dict = Depends(require_role("admin"))):
    return {"status": "ok", "user": user}

@app.get("/admin-or-manager")
async def admin_or_manager(user: dict = Depends(require_role("admin", "manager"))):
    return {"status": "ok", "user": user}

@app.get("/dept/{department_id}")
async def get_dept_data(department_id: str, user: dict = Depends(require_own_department("department_id"))):
    return {"status": "ok", "department": department_id}

client = TestClient(app)

def test_get_current_user_valid_token():
    token = create_access_token("user1", "employee", "dept_eng")
    res = client.get("/me", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    json_data = res.json()
    assert json_data["sub"] == "user1"
    assert json_data["role"] == "employee"

def test_get_current_user_missing_header():
    res = client.get("/me")
    assert res.status_code == 401
    assert res.json()["detail"]["error_code"] == "AUTH_INVALID"

def test_get_current_user_expired_token():
    token = create_access_token("user1", "employee", "dept_eng", expires_delta=timedelta(seconds=-10))
    res = client.get("/me", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 401
    assert res.json()["detail"]["error_code"] == "AUTH_EXPIRED"

def test_require_role_authorized():
    token = create_access_token("admin_user", "admin", "dept_it")
    res = client.get("/admin-only", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    assert res.json()["status"] == "ok"


def test_role_alias_is_normalized_for_rbac():
    token = create_access_token("supervisor_user", "Supervisor", "dept_ops")
    res = client.get("/admin-or-manager", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    assert res.json()["user"]["role"] == "manager"


def test_refresh_token_cannot_authorize_api_route():
    token = create_refresh_token("user1")
    res = client.get("/me", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 401
    assert res.json()["detail"]["error_code"] == "AUTH_INVALID"

def test_require_role_forbidden():
    token = create_access_token("emp_user", "employee", "dept_it")
    res = client.get("/admin-only", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 403
    assert res.json()["detail"]["error_code"] == "AUTH_FORBIDDEN"

def test_require_own_department_match():
    token = create_access_token("emp_user", "employee", "dept_eng")
    res = client.get("/dept/dept_eng", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200

def test_require_own_department_mismatch():
    token = create_access_token("emp_user", "employee", "dept_eng")
    res = client.get("/dept/dept_hr", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 403
    assert res.json()["detail"]["error_code"] == "AUTH_FORBIDDEN"

def test_require_own_department_admin_bypass():
    token = create_access_token("admin_user", "admin", "dept_it")
    res = client.get("/dept/dept_hr", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
