"""Intelligence Hub API router delivering managerial analytics dashboards."""

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, Query

from app.middleware.rbac_middleware import require_role
from app.services.analytics_service import AnalyticsService

router = APIRouter(prefix="/analytics", tags=["Intelligence Hub Analytics"])


@router.get(
    "/sop-usage",
    response_model=List[Dict[str, Any]],
    dependencies=[Depends(require_role("manager", "admin"))],
)
async def get_sop_usage(
    department_id: Optional[str] = Query(None, description="Optional department filter"),
) -> List[Dict[str, Any]]:
    """Retrieve SOP usage counts, execution metrics, and completion times."""
    return AnalyticsService.get_sop_usage(department_id=department_id)


@router.get(
    "/faqs",
    response_model=List[Dict[str, Any]],
    dependencies=[Depends(require_role("manager", "admin"))],
)
async def get_faqs(
    department_id: Optional[str] = Query(None, description="Optional department filter"),
    limit: int = Query(50, ge=1, le=200, description="Max FAQ records to return"),
) -> List[Dict[str, Any]]:
    """Retrieve top queried operational topics and average confidence ratings."""
    return AnalyticsService.get_faqs(department_id=department_id, limit=limit)


@router.get(
    "/confusing-procedures",
    response_model=List[Dict[str, Any]],
    dependencies=[Depends(require_role("manager", "admin"))],
)
async def get_confusing_procedures(
    department_id: Optional[str] = Query(None, description="Optional department filter"),
) -> List[Dict[str, Any]]:
    """Retrieve SOPs flagged for high escalation or high clarification request rates."""
    return AnalyticsService.get_confusing_procedures(department_id=department_id)


@router.get(
    "/escalations",
    response_model=List[Dict[str, Any]],
    dependencies=[Depends(require_role("manager", "admin"))],
)
async def get_escalations(
    department_id: Optional[str] = Query(None, description="Optional department filter"),
) -> List[Dict[str, Any]]:
    """Retrieve detailed human escalation logs and resolution statuses."""
    return AnalyticsService.get_escalations(department_id=department_id)


@router.get(
    "/department-adoption",
    response_model=List[Dict[str, Any]],
    dependencies=[Depends(require_role("manager", "admin"))],
)
async def get_department_adoption() -> List[Dict[str, Any]]:
    """Retrieve enterprise platform adoption metrics across departments."""
    return AnalyticsService.get_department_adoption()


@router.get(
    "/confidence-trends",
    response_model=List[Dict[str, Any]],
    dependencies=[Depends(require_role("manager", "admin"))],
)
async def get_confidence_trends(
    department_id: Optional[str] = Query(None, description="Optional department filter"),
) -> List[Dict[str, Any]]:
    """Retrieve time-series trend of average AI response confidence scores."""
    return AnalyticsService.get_confidence_trends(department_id=department_id)
