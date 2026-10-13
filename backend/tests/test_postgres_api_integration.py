"""Real FastAPI + PostgreSQL contract tests. No mocks for auth or reference persistence.

Run against the disposable PostgreSQL 16 CI service only. Every synthetic
account/document is isolated by a unique suffix and cleaned up afterward.
"""
from __future__ import annotations

import uuid

import psycopg
import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.security import hash_password
from app.main import app


@pytest.mark.live_integration
def test_real_api_login_review_search_archive_and_revocation(monkeypatch):
    prefix = uuid.uuid4().hex[:10]
    department = f"api_{prefix}"
    other_department = f"other_{prefix}"
    admin_id, employee_id, outsider_id = (f"ad_{prefix}", f"em_{prefix}", f"ot_{prefix}")
    roles = [f"ra_{prefix}", f"re_{prefix}"]
    password = "Synthetic-QA-Password-2026!"
    ids = [admin_id, employee_id, outsider_id]
    document_id = None
    source_id = None

    monkeypatch.setattr(settings, "AUTH_REVALIDATE_DB", True)
    monkeypatch.setattr(settings, "LOCAL_AI_ENABLED", False)

    with psycopg.connect(settings.DATABASE_URL, autocommit=True) as conn:
        with conn.cursor() as cur:
            for dept in (department, other_department):
                cur.execute("INSERT INTO security.departments (id,code,name) VALUES (%s,%s,%s)",
                            (dept, dept.upper(), f"QA {dept}"))
            for role_id, name in zip(roles, ("admin", "employee")):
                cur.execute("""INSERT INTO security.roles (id,name,permission_set)
                            VALUES (%s,%s,'{}'::jsonb)""", (role_id, name))
            for user_id, dept, role in [
                (admin_id, department, roles[0]), (employee_id, department, roles[1]),
                (outsider_id, other_department, roles[1]),
            ]:
                cur.execute("""INSERT INTO security.users (id,email,hashed_password,department_id)
                            VALUES (%s,%s,%s,%s)""",
                            (user_id, f"{user_id}@example.test", hash_password(password), dept))
                cur.execute("INSERT INTO security.user_roles (user_id,role_id) VALUES (%s,%s)",
                            (user_id, role))
    try:
        with TestClient(app) as client:
            tokens = {}
            for user_id in ids:
                result = client.post("/api/v1/auth/login", json={
                    "email": f"{user_id}@example.test", "password": password,
                })
                assert result.status_code == 200, result.text
                tokens[user_id] = {"Authorization": f"Bearer {result.json()['access_token']}"}
            admin = tokens[admin_id]
            employee = tokens[employee_id]
            outsider = tokens[outsider_id]

            unauth = client.get("/api/v1/knowledge/references/search?q=seal")
            assert unauth.status_code == 401
            forbidden = client.get(
                f"/api/v1/knowledge/references?department_id={department}",
                headers=employee,
            )
            assert forbidden.status_code == 403

            text = b"During receiving, inspect the security seal on every carton. If damaged, quarantine the carton and notify the supervisor before putaway."
            uploaded = client.post("/api/v1/knowledge/references", headers=admin,
                files={"file": ("receiving.txt", text, "text/plain")},
                data={"department_id": department, "title": "Controlled Receiving Guidance"},
            )
            assert uploaded.status_code == 201, uploaded.text
            document_id = uploaded.json()["id"]
            with psycopg.connect(settings.DATABASE_URL) as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT stage_uri FROM knowledge_studio.reference_documents WHERE id=%s", (document_id,))
                    row = cur.fetchone()
                    assert row and row[0].startswith("pgobj:")
                    source_id = row[0].split(":", 1)[1]

            def search(headers):
                return client.get("/api/v1/knowledge/references/search?q=security%20seal&limit=10", headers=headers)

            # Draft is invisible even to the same-department employee.
            assert search(employee).status_code == 200
            assert search(employee).json()["sources"] == []
            assert search(outsider).json()["sources"] == []

            approved = client.post(
                f"/api/v1/knowledge/references/{document_id}/approve?department_id={department}",
                headers=admin,
            )
            assert approved.status_code == 200, approved.text
            allowed = search(employee)
            assert allowed.status_code == 200 and allowed.json()["sources"], allowed.text
            assert all(s["department_id"] == department for s in allowed.json()["sources"])
            assert not search(outsider).json()["sources"]

            archived = client.post(
                f"/api/v1/knowledge/references/{document_id}/archive?department_id={department}",
                headers=admin,
            )
            assert archived.status_code == 200, archived.text
            assert search(employee).json()["sources"] == []
            with psycopg.connect(settings.DATABASE_URL) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """SELECT action FROM shared.audit_logs
                           WHERE user_id=%s AND resource=%s
                           AND action IN ('REFERENCE_APPROVE', 'REFERENCE_ARCHIVE')""",
                        (admin_id, f"reference:{department}/{document_id}"),
                    )
                    assert sorted(row[0] for row in cur.fetchall()) == [
                        "REFERENCE_APPROVE", "REFERENCE_ARCHIVE"
                    ]
            # Audit events must persist in PostgreSQL, not silently fail under
            # the legacy Snowflake UUID_STRING() function.
            with psycopg.connect(settings.DATABASE_URL) as audit_conn:
                with audit_conn.cursor() as audit_cur:
                    audit_cur.execute(
                        """SELECT count(*) FROM shared.audit_logs
                           WHERE action LIKE 'POST /api/v1/knowledge/references%'
                             AND status_code IN (200,201)""",
                    )
                    assert audit_cur.fetchone()[0] >= 3

            # Existing JWT is no longer enough after an account is disabled.
            with psycopg.connect(settings.DATABASE_URL, autocommit=True) as conn:
                with conn.cursor() as cur:
                    cur.execute("UPDATE security.users SET status='disabled' WHERE id=%s", (employee_id,))
            blocked = client.get("/api/v1/auth/me", headers=employee)
            assert blocked.status_code == 401, blocked.text
            assert blocked.json()["detail"]["error_code"] == "AUTH_STALE"
            assert client.get("/api/v1/auth/me", headers=admin).status_code == 200
    finally:
        with psycopg.connect(settings.DATABASE_URL, autocommit=True) as conn:
            with conn.cursor() as cur:
                if document_id:
                    cur.execute("DELETE FROM knowledge_studio.reference_chunks WHERE document_id=%s", (document_id,))
                    cur.execute("DELETE FROM knowledge_studio.reference_documents WHERE id=%s", (document_id,))
                # Always clean up scoped source bytes, even if an assertion
                # failed before the test could read the uploaded object ID.
                cur.execute("DELETE FROM shared.source_objects WHERE department_id=%s", (department,))
                cur.execute("DELETE FROM security.user_roles WHERE user_id = ANY(%s)", (ids,))
                cur.execute("DELETE FROM security.users WHERE id = ANY(%s)", (ids,))
                cur.execute("DELETE FROM security.roles WHERE id = ANY(%s)", (roles,))
                cur.execute("DELETE FROM security.departments WHERE id = ANY(%s)",
                            ([department, other_department],))
