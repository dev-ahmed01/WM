"""Real PostgreSQL pilot feedback contract: employee isolation, aggregate-only manager view."""
from __future__ import annotations

import uuid

import psycopg
import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.security import create_access_token, hash_password
from app.main import app


@pytest.mark.live_integration
def test_scoped_pilot_feedback_and_manager_aggregation(monkeypatch):
    suffix = uuid.uuid4().hex[:9]
    dept_a, dept_b = f"pilot_{suffix}", f"other_{suffix}"
    emp_a, mgr_a, emp_b = (f"emp_{suffix}",f"mgr_{suffix}",f"ext_{suffix}")
    role_emp, role_mgr = (f"remp_{suffix}",f"rmgr_{suffix}")
    users = [emp_a, mgr_a, emp_b]
    roles = [role_emp, role_mgr]
    monkeypatch.setattr(settings, "PILOT_FEEDBACK_ENABLED", True)
    monkeypatch.setattr(settings, "PILOT_ALLOWED_DEPARTMENTS", dept_a)
    monkeypatch.setattr(settings, "PILOT_FEEDBACK_MAX_PER_USER_PER_DAY", 2)
    with psycopg.connect(settings.DATABASE_URL, autocommit=True) as conn:
        with conn.cursor() as cur:
            for dept in (dept_a, dept_b):
                cur.execute("INSERT INTO security.departments (id,code,name) VALUES (%s,%s,%s)",
                            (dept,dept.upper(),dept))
            for role, name in ((role_emp,"employee"),(role_mgr,"manager")):
                cur.execute("INSERT INTO security.roles (id,name,permission_set) VALUES (%s,%s,'{}'::jsonb)",
                            (role,name))
            for user, dept, role in ((emp_a,dept_a,role_emp),(mgr_a,dept_a,role_mgr),
                                     (emp_b,dept_b,role_emp)):
                cur.execute("""INSERT INTO security.users (id,email,hashed_password,department_id)
                               VALUES (%s,%s,%s,%s)""",
                            (user,f"{user}@example.test",hash_password("test-secret-only"),dept))
                cur.execute("INSERT INTO security.user_roles (user_id,role_id) VALUES (%s,%s)", (user,role))
    def hdr(user, role, dept):
        return {"Authorization":f"Bearer {create_access_token(user,role,dept)}"}
    try:
        with TestClient(app) as client:
            employee = hdr(emp_a,"employee",dept_a)
            manager = hdr(mgr_a,"manager",dept_a)
            outsider = hdr(emp_b,"employee",dept_b)
            good = {"surface":"reference","verdict":"helpful","issue":"none"}
            bad = {"surface":"workflow","verdict":"needs_review","issue":"unsafe_step"}
            assert client.post("/api/v1/pilot/feedback",headers=employee,json=good).status_code == 201
            assert client.post("/api/v1/pilot/feedback",headers=employee,json=bad).status_code == 201
            assert client.post("/api/v1/pilot/feedback",headers=employee,json=good).status_code == 429
            assert client.post("/api/v1/pilot/feedback",headers=outsider,json=bad).status_code == 404
            assert client.get("/api/v1/pilot/summary",headers=employee).status_code == 403
            approved = client.get("/api/v1/pilot/summary?days=14",headers=manager)
            assert approved.status_code == 200, approved.text
            summary = approved.json()
            assert (summary["total"], summary["needs_review"], summary["helpful"]) == (2,1,1)
            assert "reporter_user_id" not in str(summary)
            assert "unsafe_step" in str(summary)
            with psycopg.connect(settings.DATABASE_URL) as conn:
                with conn.cursor() as cur:
                    cur.execute("""SELECT DISTINCT department_id,reporter_user_id
                                   FROM shared.pilot_feedback WHERE department_id=%s""", (dept_a,))
                    assert cur.fetchall() == [(dept_a, emp_a)]
    finally:
        with psycopg.connect(settings.DATABASE_URL, autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM shared.pilot_feedback WHERE reporter_user_id=ANY(%s)", (users,))
                cur.execute("DELETE FROM security.user_roles WHERE user_id=ANY(%s)", (users,))
                cur.execute("DELETE FROM security.users WHERE id=ANY(%s)", (users,))
                cur.execute("DELETE FROM security.roles WHERE id=ANY(%s)", (roles,))
                cur.execute("DELETE FROM security.departments WHERE id=ANY(%s)", ([dept_a,dept_b],))
