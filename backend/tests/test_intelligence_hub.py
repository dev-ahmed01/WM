"""Unit tests for Intelligence Hub analytics endpoints and service layer."""

import pytest
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.intelligence import router as intelligence_router
from app.core.security import create_access_token
from app.services.analytics_service import AnalyticsService

app = FastAPI()
app.include_router(intelligence_router, prefix="/api/v1")

client = TestClient(app)

MANAGER_TOKEN = create_access_token(user_id="usr_mgr001", role="manager", department_id="dept_eng")
EMPLOYEE_TOKEN = create_access_token(user_id="usr_emp001", role="employee", department_id="dept_eng")


@patch.object(AnalyticsService, "get_sop_usage")
def test_get_sop_usage_manager_access(mock_get_usage):
    mock_get_usage.return_value = [
        {"sop_id": "sop_101", "sop_title": "Valve SOP", "department_id": "dept_eng", "total_executions": 42}
    ]

    res = client.get(
        "/api/v1/analytics/sop-usage",
        headers={"Authorization": f"Bearer {MANAGER_TOKEN}"},
    )

    assert res.status_code == 200
    data = res.json()
    assert len(data) == 1
    assert data[0]["sop_id"] == "sop_101"


@patch.object(AnalyticsService, "get_confusing_procedures")
def test_get_confusing_procedures_manager_access(mock_get_confusing):
    mock_get_confusing.return_value = [
        {"sop_id": "sop_202", "sop_title": "Complex Turbine SOP", "confusion_rate_pct": 24.5}
    ]

    res = client.get(
        "/api/v1/analytics/confusing-procedures",
        headers={"Authorization": f"Bearer {MANAGER_TOKEN}"},
    )

    assert res.status_code == 200
    data = res.json()
    assert data[0]["confusion_rate_pct"] == 24.5


@patch.object(AnalyticsService, "get_confidence_trends")
def test_get_confidence_trends_manager_access(mock_get_trends):
    mock_get_trends.return_value = [
        {"metric_date": "2026-08-01", "avg_confidence_score": 0.93}
    ]

    res = client.get(
        "/api/v1/analytics/confidence-trends",
        headers={"Authorization": f"Bearer {MANAGER_TOKEN}"},
    )

    assert res.status_code == 200
    assert res.json()[0]["avg_confidence_score"] == 0.93


def test_analytics_forbidden_for_employee_role():
    res = client.get(
        "/api/v1/analytics/sop-usage",
        headers={"Authorization": f"Bearer {EMPLOYEE_TOKEN}"},
    )
    assert res.status_code == 403
