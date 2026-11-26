"""Intelligence Hub API router delivering managerial analytics dashboards."""

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, Query

from app.middleware.auth_middleware import get_current_user
from app.middleware.rbac_middleware import require_role
from app.middleware.tenant_scope import DepartmentScope, department_scope
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
