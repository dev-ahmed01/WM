"""Live PostgreSQL gates for organization isolation and employee onboarding."""
from __future__ import annotations

import uuid

import psycopg
import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.database import close_postgres_pool
from app.core.security import create_access_token, hash_password
from app.main import app

PASSWORD = "Sufficiently-Long-Test-Pass-1"


def _hdr(user_id: str, role: str, dept: str) -> dict:
    return {"Authorization": f"Bearer {create_access_token(user_id, role, dept)}"}


@pytest.fixture()
def tenants():
    s = uuid.uuid4().hex[:8]
    ids = {
        "orgA": f"orgA_{s}", "orgB": f"orgB_{s}", "whA": f"whA_{s}", "whB": f"whB_{s}",
        "deptA": f"deptA_{s}", "deptB": f"deptB_{s}",
        "adminA": f"admA_{s}", "adminB": f"admB_{s}", "empA": f"empA_{s}", "empB": f"empB_{s}",
        "mgrA": f"mgrA_{s}",
    }
    with psycopg.connect(settings.DATABASE_URL, autocommit=True) as conn, conn.cursor() as cur:
        for k in ("A", "B"):
            cur.execute("INSERT INTO security.organizations (id,code,name) VALUES (%s,%s,%s)",
                        (ids["org" + k], ids["org" + k].upper(), f"Org {k}"))
            cur.execute("INSERT INTO security.warehouses (id,organization_id,code,name) VALUES (%s,%s,'W1','Main')",
                        (ids["wh" + k], ids["org" + k]))
            cur.execute("INSERT INTO security.departments (id,code,name,organization_id,warehouse_id) "
                        "VALUES (%s,%s,%s,%s,%s)",
                        (ids["dept" + k], ids["dept" + k].upper(), f"Dept {k}", ids["org" + k], ids["wh" + k]))
        for key, dept, role in (("adminA", "deptA", "role_admin"), ("adminB", "deptB", "role_admin"),
                                ("empA", "deptA", "role_employee"), ("empB", "deptB", "role_employee"),
                                ("mgrA", "deptA", "role_manager")):
            cur.execute("INSERT INTO security.users (id,email,hashed_password,department_id) VALUES (%s,%s,%s,%s)",
                        (ids[key], f"{ids[key]}@example.test", hash_password(PASSWORD), ids[dept]))
            cur.execute("SELECT id FROM security.roles WHERE LOWER(name)=%s LIMIT 1", (role.removeprefix("role_"),))
            cur.execute("INSERT INTO security.user_roles (user_id,role_id) VALUES (%s,%s) ON CONFLICT DO NOTHING",
                        (ids[key], cur.fetchone()[0]))
    yield ids
    close_postgres_pool()
    with psycopg.connect(settings.DATABASE_URL, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM security.account_tokens WHERE user_id IN (SELECT id FROM security.users WHERE department_id IN (%s,%s))",
                    (ids["deptA"], ids["deptB"]))
        cur.execute("DELETE FROM security.refresh_sessions WHERE user_id IN (SELECT id FROM security.users WHERE department_id IN (%s,%s))",
                    (ids["deptA"], ids["deptB"]))
        cur.execute("DELETE FROM security.user_roles WHERE user_id IN (SELECT id FROM security.users WHERE department_id IN (%s,%s))",
                    (ids["deptA"], ids["deptB"]))
        cur.execute("UPDATE security.users SET supervisor_id=NULL WHERE department_id IN (%s,%s)", (ids["deptA"], ids["deptB"]))
        cur.execute("DELETE FROM security.users WHERE department_id IN (%s,%s)", (ids["deptA"], ids["deptB"]))
        cur.execute("DELETE FROM security.departments WHERE id IN (%s,%s)", (ids["deptA"], ids["deptB"]))
        cur.execute("DELETE FROM security.warehouses WHERE id IN (%s,%s)", (ids["whA"], ids["whB"]))
        cur.execute("DELETE FROM security.organizations WHERE id IN (%s,%s)", (ids["orgA"], ids["orgB"]))


@pytest.mark.live_integration
def test_admin_cannot_see_or_touch_other_organization(tenants):
    t = tenants
    a = _hdr(t["adminA"], "admin", t["deptA"])
    with TestClient(app) as client:
        listed = client.get("/api/v1/admin/employees", headers=a).json()
        emails = {e["email"] for e in listed}
        assert f"{t['empA']}@example.test" in emails
        assert f"{t['empB']}@example.test" not in emails

        # Direct-object references into the other organization look like 404.
        assert client.patch(f"/api/v1/admin/employees/{t['empB']}", headers=a, json={"full_name": "x"}).status_code == 404
        assert client.post(f"/api/v1/admin/employees/{t['empB']}/status", headers=a, json={"active": False}).status_code == 404
        assert client.post(f"/api/v1/admin/employees/{t['empB']}/recovery-token", headers=a).status_code == 404

        base = {"email": f"new_{t['empA']}@example.test", "full_name": "N", "department_id": t["deptB"]}
        assert client.post("/api/v1/admin/employees", headers=a, json=base).status_code == 404  # foreign dept
        ok = {**base, "department_id": t["deptA"], "warehouse_id": t["whB"]}
        assert client.post("/api/v1/admin/employees", headers=a, json=ok).status_code == 404     # foreign warehouse
        sup = {**base, "department_id": t["deptA"], "supervisor_id": t["empB"]}
        assert client.post("/api/v1/admin/employees", headers=a, json=sup).status_code == 404    # foreign supervisor

        overview = client.get("/api/v1/admin/org", headers=a).json()
        assert overview["organization"]["id"] == t["orgA"]
        assert {d["id"] for d in overview["departments"]} == {t["deptA"]}


@pytest.mark.live_integration
def test_non_admin_roles_are_denied(tenants):
    t = tenants
    with TestClient(app) as client:
        for who, role, dept in (("empA", "employee", "deptA"), ("mgrA", "manager", "deptA")):
            h = _hdr(t[who], role, t[dept])
            assert client.get("/api/v1/admin/employees", headers=h).status_code == 403
            assert client.post("/api/v1/admin/employees", headers=h, json={}).status_code in (403, 422)
        assert client.get("/api/v1/admin/employees").status_code == 401


@pytest.mark.live_integration
def test_database_rejects_cross_org_supervisor(tenants):
    t = tenants
    with psycopg.connect(settings.DATABASE_URL, autocommit=True) as conn, conn.cursor() as cur:
        with pytest.raises(psycopg.errors.CheckViolation):
            cur.execute("UPDATE security.users SET supervisor_id=%s WHERE id=%s", (t["empB"], t["empA"]))
        with pytest.raises(psycopg.errors.CheckViolation):
            cur.execute("UPDATE security.users SET warehouse_id=%s WHERE id=%s", (t["whB"], t["empA"]))


@pytest.mark.live_integration
def test_invite_login_deactivate_and_recovery_flow(tenants):
    t = tenants
    a = _hdr(t["adminA"], "admin", t["deptA"])
    email = f"invitee_{t['empA']}@example.test"
    with TestClient(app) as client:
        r = client.post("/api/v1/admin/employees", headers=a, json={
            "email": email, "full_name": "Invitee", "department_id": t["deptA"],
            "job_profile": "PICKER", "warehouse_id": t["whA"], "supervisor_id": t["mgrA"],
            "preferred_language": "hinglish"})
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["employee"]["status"] == "invited" and body["employee"]["job_profile"] == "PICKER"
        token, uid = body["one_time_token"], body["employee"]["id"]

        # Invited accounts cannot sign in before accepting.
        assert client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD}).status_code == 401
        assert client.post("/api/v1/auth/token/redeem", json={"token": token, "password": "short"}).status_code == 422
        assert client.post("/api/v1/auth/token/redeem", json={"token": token, "password": PASSWORD}).status_code == 200
        assert client.post("/api/v1/auth/token/redeem", json={"token": token, "password": PASSWORD}).status_code == 400  # one-time
        assert client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD}).status_code == 200

        # Deactivation blocks sign-in and cannot be bypassed by a recovery token.
        assert client.post(f"/api/v1/admin/employees/{uid}/status", headers=a, json={"active": False}).status_code == 200
        assert client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD}).status_code == 401
        rec = client.post(f"/api/v1/admin/employees/{uid}/recovery-token", headers=a).json()["one_time_token"]
        assert client.post("/api/v1/auth/token/redeem", json={"token": rec, "password": PASSWORD + "x"}).status_code == 422
        assert client.post("/api/v1/admin/employees/%s/status" % uid, headers=a, json={"active": True}).status_code == 200
        rec2 = client.post(f"/api/v1/admin/employees/{uid}/recovery-token", headers=a).json()["one_time_token"]
        assert client.post("/api/v1/auth/token/redeem", json={"token": rec2, "password": PASSWORD + "x"}).status_code == 200
        assert client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD + "x"}).status_code == 200


@pytest.mark.live_integration
def test_escalations_are_scoped_to_organization_and_manager_department(tenants):
    t = tenants
    s = t["deptA"].split("_")[1]
    dept_a2 = f"deptA2_{s}"
    esc = {"A": f"escA_{s}", "A2": f"escA2_{s}", "B": f"escB_{s}"}
    with psycopg.connect(settings.DATABASE_URL, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute("INSERT INTO security.departments (id,code,name,organization_id) VALUES (%s,%s,'A2',%s)",
                    (dept_a2, dept_a2.upper(), t["orgA"]))
        for key, dept, user in (("A", t["deptA"], t["empA"]), ("A2", dept_a2, t["empA"]), ("B", t["deptB"], t["empB"])):
            cur.execute("INSERT INTO workmate_copilot.conversations (id,user_id,department_id) VALUES (%s,%s,%s)",
                        (f"cv_{key}_{s}", user, dept))
            cur.execute("INSERT INTO workmate_copilot.conversation_messages (id,conversation_id,sender,message_text) "
                        "VALUES (%s,%s,'employee','help')", (f"msg_{key}_{s}", f"cv_{key}_{s}"))
            cur.execute("INSERT INTO workmate_copilot.escalation_records (id,conversation_message_id,reason,status) "
                        "VALUES (%s,%s,'test','open')", (esc[key], f"msg_{key}_{s}"))
        # Orphan escalation with no conversation link must stay invisible.
        cur.execute("INSERT INTO workmate_copilot.escalation_records (id,reason,status) VALUES (%s,'orphan','open')",
                    (f"escO_{s}",))
    try:
        admin = _hdr(t["adminA"], "admin", t["deptA"])
        mgr = _hdr(t["mgrA"], "manager", t["deptA"])
        with TestClient(app) as client:
            ids = {e["id"] for e in client.get("/api/v1/escalations", headers=admin).json()}
            assert {esc["A"], esc["A2"]} <= ids and esc["B"] not in ids and f"escO_{s}" not in ids
            mids = {e["id"] for e in client.get("/api/v1/escalations", headers=mgr).json()}
            assert mids == {esc["A"]}
            assert client.post(f"/api/v1/escalations/{esc['B']}/resolve", headers=admin,
                               json={"resolution_note": "x"}).status_code == 404
            assert client.post(f"/api/v1/escalations/{esc['A2']}/resolve", headers=mgr,
                               json={"resolution_note": "x"}).status_code == 404
            assert client.post(f"/api/v1/escalations/{esc['A']}/resolve", headers=mgr,
                               json={"resolution_note": "done"}).status_code == 200
    finally:
        close_postgres_pool()
        with psycopg.connect(settings.DATABASE_URL, autocommit=True) as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM workmate_copilot.escalation_records WHERE id LIKE %s OR conversation_message_id LIKE %s",
                        (f"%{s}", f"%{s}"))
            cur.execute("DELETE FROM workmate_copilot.conversation_messages WHERE id LIKE %s", (f"msg_%_{s}",))
            cur.execute("DELETE FROM workmate_copilot.conversations WHERE id LIKE %s", (f"cv_%_{s}",))
            cur.execute("DELETE FROM security.departments WHERE id=%s", (dept_a2,))
