"""Administrator employee management and account onboarding/recovery.

Admin routes are scoped to the acting administrator's organization, resolved
from the database. Out-of-organization targets are reported as 404 so object
existence is never disclosed across tenants.
"""
from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field, StringConstraints
from typing_extensions import Annotated
from starlette.concurrency import run_in_threadpool

from app.core.config import settings
from app.middleware.rbac_middleware import require_role
from app.repositories.org_repository import OrgRepository, OrgScopeError, OrgValidationError
from app.repositories.session_security_repository import AuthThrottleRepository

router = APIRouter(tags=["Employee management"])
admin_only = Depends(require_role("admin"))
Language = Literal["en", "hi", "hinglish"]
Email = Annotated[str, StringConstraints(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$", max_length=255)]


class EmployeeCreate(BaseModel):
    email: Email
    full_name: str = Field(min_length=1, max_length=255)
    department_id: str
    role: Literal["employee", "manager"] = "employee"
    job_profile: Optional[str] = None
    warehouse_id: Optional[str] = None
    supervisor_id: Optional[str] = None
    preferred_language: Language = "en"


class EmployeeUpdate(BaseModel):
    full_name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    department_id: Optional[str] = None
    role: Optional[Literal["employee", "manager"]] = None
    job_profile: Optional[str] = None
    warehouse_id: Optional[str] = None
    supervisor_id: Optional[str] = None
    preferred_language: Optional[Language] = None


class StatusChange(BaseModel):
    active: bool


class TokenRedeem(BaseModel):
    token: str = Field(min_length=20, max_length=200)
    password: str = Field(min_length=12, max_length=128)


def _http(exc: Exception) -> HTTPException:
    if isinstance(exc, OrgScopeError):
        return HTTPException(404, detail={"error_code": "NOT_FOUND", "message": "Not found in your organization."})
    return HTTPException(422, detail={"error_code": "VALIDATION_ERROR", "message": str(exc)})


async def _call(fn, *args, **kwargs):
    try:
        return await run_in_threadpool(fn, *args, **kwargs)
    except (OrgScopeError, OrgValidationError) as exc:
        raise _http(exc) from exc


@router.get("/admin/org")
async def organization_overview(user: Dict[str, Any] = admin_only):
    return await _call(OrgRepository.overview, user["sub"])


@router.get("/admin/employees")
async def list_employees(q: str = "", limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0),
                         user: Dict[str, Any] = admin_only) -> List[Dict[str, Any]]:
    return await _call(OrgRepository.list_employees, user["sub"], q, limit, offset)


@router.post("/admin/employees", status_code=201)
async def create_employee(body: EmployeeCreate, user: Dict[str, Any] = admin_only):
    """Create an invited employee. The one-time token is shown once; it is not emailed by WorkMate."""
    return await _call(OrgRepository.create_invited, user["sub"], body.model_dump())


@router.patch("/admin/employees/{employee_id}")
async def update_employee(employee_id: str, body: EmployeeUpdate, user: Dict[str, Any] = admin_only):
    return await _call(OrgRepository.update_employee, user["sub"], employee_id,
                       body.model_dump(exclude_unset=True))


@router.post("/admin/employees/{employee_id}/status")
async def change_status(employee_id: str, body: StatusChange, user: Dict[str, Any] = admin_only):
    return await _call(OrgRepository.set_active, user["sub"], employee_id, body.active)


@router.post("/admin/employees/{employee_id}/recovery-token")
async def recovery_token(employee_id: str, user: Dict[str, Any] = admin_only):
    return await _call(OrgRepository.issue_recovery, user["sub"], employee_id)


@router.post("/auth/token/redeem")
async def redeem_token(body: TokenRedeem, request: Request) -> Dict[str, bool]:
    """Public: accept an invitation or finish recovery by setting a password."""
    if settings.AUTH_RATE_LIMIT_ENABLED:
        permitted = await run_in_threadpool(
            AuthThrottleRepository.consume, "redeem", "token",
            request.client.host if request.client else "unresolved")
        if not permitted:
            raise HTTPException(429, detail={"error_code": "AUTH_RATE_LIMITED",
                                             "message": "Too many attempts. Try again later."})
    try:
        ok = await run_in_threadpool(OrgRepository.redeem_token, body.token, body.password)
    except OrgValidationError as exc:
        raise _http(exc) from exc
    if not ok:
        raise HTTPException(400, detail={"error_code": "TOKEN_INVALID",
                                         "message": "The link is invalid, expired or already used."})
    return {"password_set": True}
