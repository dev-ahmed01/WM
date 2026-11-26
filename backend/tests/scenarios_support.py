"""Shared world for the end-to-end acceptance scenarios (scratch database, real HTTP stack)."""
from __future__ import annotations

import hashlib
from typing import Dict

import psycopg
from fastapi.testclient import TestClient

from app.core.security import create_access_token, hash_password

PASSWORD = "x" * 14
ORG_A, DEPT_A = "org_a", "dept_a"
ORG_B, DEPT_B = "org_b", "dept_b"
USERS = (  # id, role, department
    ("admin1", "admin", DEPT_A), ("admin2", "admin", DEPT_A), ("mgr", "manager", DEPT_A),
    ("emp1", "employee", DEPT_A), ("emp2", "employee", DEPT_A),
    ("admin_b", "admin", DEPT_B), ("emp_b", "employee", DEPT_B),
)
ROLE = {u: (r, d) for u, r, d in USERS}


def seed_world(dsn: str) -> None:
    with psycopg.connect(dsn, autocommit=True) as conn, conn.cursor() as cur:
        for org, dept in ((ORG_A, DEPT_A), (ORG_B, DEPT_B)):
            cur.execute("INSERT INTO security.organizations (id,code,name) VALUES (%s,%s,%s)", (org, org.upper(), org))
            cur.execute("INSERT INTO security.departments (id,code,name,organization_id) VALUES (%s,%s,%s,%s)",
                        (dept, dept.upper(), dept, org))
        for uid, role, dept in USERS:
            cur.execute("INSERT INTO security.users (id,email,hashed_password,department_id,full_name) VALUES (%s,%s,%s,%s,%s)",
                        (uid, f"{uid}@example.test", hash_password(PASSWORD), dept, uid))
            cur.execute("INSERT INTO security.user_roles (user_id,role_id) SELECT %s, id FROM security.roles WHERE name=%s", (uid, role))


def publish_markdown(md: str, dept: str, title: str, actor: str = "admin1") -> dict:
    from app.compiler.pipeline import OWDCompilerPipeline
    from app.services.ingestion import IngestionService
    raw = md.encode()
    code = hashlib.sha256(raw).hexdigest()[:10]
    uri = IngestionService.stage_file(raw, f"{code}.md", f"scn/{code}", department_id=dept)
    report = OWDCompilerPipeline.process_owd(markdown_text=md, title=title, department_id=dept, user_id=actor,
                                             stage_file_uri=uri, version_number=1)
    assert report["compilation_status"] == "SUCCESS", report
    return report


def publish_demo_library(dept: str) -> None:
    from demo.sop_catalog import CATALOG, DEMO_DEPARTMENT_ID
    from demo.sop_generator import render
    for sop in CATALOG:
        publish_markdown(render(sop).replace(DEMO_DEPARTMENT_ID, dept), dept, sop.title)


def publish_org_b_sop(dept: str) -> None:
    from demo.sop_catalog import CATALOG, DEMO_DEPARTMENT_ID
    from demo.sop_generator import render
    md = (render(CATALOG[0]).replace(DEMO_DEPARTMENT_ID, dept).replace("SOP-INB-001", "SOP-ORGB-001")
          .replace("Supplier arrival and gate check", "Quarantine of purple widgets"))
    publish_markdown(md, dept, "Quarantine of purple widgets", actor="admin_b")


def headers(user: str) -> Dict[str, str]:
    role, dept = ROLE[user]
    return {"Authorization": "Bearer " + create_access_token(user, role, dept)}


class Api:
    """Tiny helper around TestClient that always authenticates as a named user."""

    def __init__(self, client: TestClient):
        self.c = client

    def ask(self, user: str, message: str, conversation_id: str | None = None) -> dict:
        r = self.c.post("/api/v1/copilot/message", headers=headers(user),
                        json={"message": message, **({"conversation_id": conversation_id} if conversation_id else {})})
        assert r.status_code == 200, (message, r.status_code, r.text)
        return r.json()

    def get(self, user: str, path: str, **kw):
        return self.c.get("/api/v1" + path, headers=headers(user), **kw)

    def post(self, user: str, path: str, json=None, **kw):
        return self.c.post("/api/v1" + path, headers=headers(user), json=json, **kw)

    def put(self, user: str, path: str, json=None):
        return self.c.put("/api/v1" + path, headers=headers(user), json=json)


def provision_runtime_role(owner_dsn: str) -> tuple[str, str]:
    """Create a production-shaped runtime login (NOT the owner, no BYPASSRLS) using the project's own grants script.
    Returns (runtime_dsn, role_name). Row-level security therefore applies exactly as it does in staging/production."""
    import importlib.util
    import uuid
    from pathlib import Path
    from urllib.parse import urlsplit, urlunsplit

    role = "wm_rt_" + uuid.uuid4().hex[:8]
    parts = urlsplit(owner_dsn)
    runtime_dsn = urlunsplit(parts._replace(netloc=f"{role}:rt-test-pass-9@{parts.hostname}:{parts.port or 5432}"))
    with psycopg.connect(owner_dsn, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute("SELECT 1 FROM pg_roles WHERE rolname='workmate_scoped_reader'")
        if not cur.fetchone():
            cur.execute("CREATE ROLE workmate_scoped_reader NOLOGIN")
        cur.execute(f"CREATE ROLE {role} LOGIN PASSWORD 'rt-test-pass-9' NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE")
    spec = importlib.util.spec_from_file_location("grant_pg_runtime", Path(__file__).resolve().parents[2] / "scripts" / "grant_pg_runtime.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.provision(owner_dsn, runtime_dsn)
    return runtime_dsn, role


def drop_runtime_role(owner_dsn: str, role: str) -> None:
    with psycopg.connect(owner_dsn, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute(f"DROP OWNED BY {role}")
        cur.execute(f"DROP ROLE IF EXISTS {role}")
