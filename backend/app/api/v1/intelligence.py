"""Intelligence Hub API router delivering managerial analytics dashboards."""

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from starlette.concurrency import run_in_threadpool

from app.middleware.auth_middleware import get_current_user
from app.middleware.rbac_middleware import require_role
from app.middleware.tenant_scope import DepartmentScope, department_scope
from app.services import metrics_service
from app.services.analytics_service import AnalyticsService

router = APIRouter(prefix="/analytics", tags=["Intelligence Hub Analytics"])


def analytics_departments(
    department_id: Optional[str] = Query(None, description="Optional department filter within your scope"),
    user: Dict[str, Any] = Depends(get_current_user),
    scope: DepartmentScope = Depends(department_scope),
) -> List[str]:
    """Departments the caller may see. Admins: their organization. Managers: their own department only.
    A requested department outside that scope is a 404, never silently widened."""
    allowed = sorted(scope.allowed) if user.get("role") == "admin" else [str(user.get("department_id") or "")]
    if department_id:
        if department_id not in allowed:
            scope.ensure(None)  # raises the standard 404
        return [department_id]
    return [d for d in allowed if d]


@router.get(
    "/sop-usage",
    response_model=List[Dict[str, Any]],
    dependencies=[Depends(require_role("manager", "admin"))],
)
async def get_sop_usage(departments: List[str] = Depends(analytics_departments)) -> List[Dict[str, Any]]:
    """Retrieve SOP usage counts, execution metrics, and completion times."""
    return AnalyticsService.get_sop_usage(department_ids=departments)


@router.get(
    "/faqs",
    response_model=List[Dict[str, Any]],
    dependencies=[Depends(require_role("manager", "admin"))],
)
async def get_faqs(
    departments: List[str] = Depends(analytics_departments),
    limit: int = Query(50, ge=1, le=200, description="Max FAQ records to return"),
) -> List[Dict[str, Any]]:
    """Retrieve top queried operational topics and average confidence ratings."""
    return AnalyticsService.get_faqs(department_ids=departments, limit=limit)


@router.get(
    "/confusing-procedures",
    response_model=List[Dict[str, Any]],
    dependencies=[Depends(require_role("manager", "admin"))],
)
async def get_confusing_procedures(departments: List[str] = Depends(analytics_departments)) -> List[Dict[str, Any]]:
    """Retrieve SOPs flagged for high escalation or high clarification request rates."""
    return AnalyticsService.get_confusing_procedures(department_ids=departments)


@router.get(
    "/escalations",
    response_model=List[Dict[str, Any]],
    dependencies=[Depends(require_role("manager", "admin"))],
)
async def get_escalations(departments: List[str] = Depends(analytics_departments)) -> List[Dict[str, Any]]:
    """Retrieve detailed human escalation logs and resolution statuses."""
    return AnalyticsService.get_escalations(department_ids=departments)


@router.get(
    "/department-adoption",
    response_model=List[Dict[str, Any]],
    dependencies=[Depends(require_role("manager", "admin"))],
)
async def get_department_adoption(departments: List[str] = Depends(analytics_departments)) -> List[Dict[str, Any]]:
    """Platform adoption for the departments in your scope."""
    return AnalyticsService.get_department_adoption(department_ids=departments)


@router.get(
    "/confidence-trends",
    response_model=List[Dict[str, Any]],
    dependencies=[Depends(require_role("manager", "admin"))],
)
async def get_confidence_trends(departments: List[str] = Depends(analytics_departments)) -> List[Dict[str, Any]]:
    """Retrieve time-series trend of average AI response confidence scores."""
    return AnalyticsService.get_confidence_trends(department_ids=departments)


@router.get("/summary", dependencies=[Depends(require_role("manager", "admin"))])
async def get_summary(
    days: int = Query(30, ge=1, le=365, description="Look-back window in days"),
    departments: List[str] = Depends(analytics_departments),
) -> Dict[str, Any]:
    """Measured KPIs for your scope, each with its definition. Unavailable metrics are listed, never invented."""
    return await run_in_threadpool(metrics_service.summary, departments, days)


class RoiInputs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    employees: int = Field(ge=1, le=1_000_000)
    questions_per_employee_per_week: float = Field(ge=0, le=500)
    minutes_per_supervisor_interruption: float = Field(ge=0, le=240)
    share_answered_without_supervisor_pct: float = Field(ge=0, le=100)
    loaded_hourly_cost: float = Field(ge=0, le=100000)
    weeks: int = Field(default=52, ge=1, le=52)


@router.post("/roi-estimate", dependencies=[Depends(require_role("manager", "admin"))])
async def roi_estimate(body: RoiInputs) -> Dict[str, Any]:
    """An ESTIMATE computed purely from the supplied assumptions (nothing measured)."""
    return metrics_service.roi_estimate(**body.model_dump())
