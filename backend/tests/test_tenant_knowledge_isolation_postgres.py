"""An administrator must not read or write knowledge in another organization (IDOR gate)."""
from __future__ import annotations

import hashlib

import psycopg
import pytest
from fastapi.testclient import TestClient

from app.core.security import create_access_token, hash_password
from test_knowledge_loop_postgres import scratch  # noqa: F401  (fixture)

OWD_DIR = "backend/tests/fixtures/owd_repository/inbound/receive_shipment_v1_1.md"


def _seed_two_orgs(dsn: str) -> None:
    with psycopg.connect(dsn, autocommit=True) as conn, conn.cursor() as cur:
        for k in ("a", "b"):
            cur.execute("INSERT INTO security.organizations (id,code,name) VALUES (%s,%s,%s)", (f"org_{k}", k.upper(), f"Org {k}"))
            cur.execute("INSERT INTO security.departments (id,code,name,organization_id) VALUES (%s,%s,%s,%s)",
                        (f"dept_{k}", k.upper(), f"Dept {k}", f"org_{k}"))
            cur.execute("INSERT INTO security.users (id,email,hashed_password,department_id,full_name) VALUES (%s,%s,%s,%s,%s)",
                        (f"admin_{k}", f"admin_{k}@example.test", hash_password("x" * 14), f"dept_{k}", f"Admin {k}"))
            cur.execute("INSERT INTO security.user_roles (user_id,role_id) SELECT %s, id FROM security.roles WHERE name='admin'", (f"admin_{k}",))


def _publish(dept: str, code: str) -> None:
    from app.compiler.pipeline import OWDCompilerPipeline
    from app.services.ingestion import IngestionService
    from demo.sop_catalog import CATALOG
    from demo.sop_generator import render
    md = render(CATALOG[0]).replace("SOP-INB-001", code).replace("dm_ops", dept)
    raw = md.encode()
    uri = IngestionService.stage_file(raw, f"{code}.md", f"{code}/v1/{hashlib.sha256(raw).hexdigest()[:8]}", department_id=dept)
    assert OWDCompilerPipeline.process_owd(markdown_text=md, title="T " + code, department_id=dept,
                                           user_id=f"admin_{dept[-1]}", stage_file_uri=uri, version_number=1)["compilation_status"] == "SUCCESS"


def _h(k: str) -> dict:
    return {"Authorization": "Bearer " + create_access_token(f"admin_{k}", "admin", f"dept_{k}")}


@pytest.mark.live_integration
def test_admin_cannot_touch_other_organizations_knowledge(scratch):  # noqa: F811
    from app.core.config import settings
    from app.main import app
    settings.AUTH_REVALIDATE_DB = False
    _seed_two_orgs(scratch)
    _publish("dept_a", "SOP-ISO-A1")
    _publish("dept_b", "SOP-ISO-B1")
    a = _h("a")
    with TestClient(app) as c:
        mine = c.get("/api/v1/knowledge", headers=a).json()
        codes = {i["item"]["workflow_code"] for i in mine["items"]}
        assert codes == {"SOP_ISO_A1"}, codes
        assert c.get("/api/v1/knowledge?department_id=dept_b", headers=a).status_code == 404
        assert [d["id"] for d in c.get("/api/v1/knowledge/departments", headers=a).json()] == ["dept_a"]

        other_id = next(i["item"]["id"] for i in c.get("/api/v1/knowledge", headers=_h("b")).json()["items"])
        for method, url, kw in (("GET", f"/api/v1/knowledge/{other_id}", {}),
                                ("GET", f"/api/v1/knowledge/{other_id}/versions", {}),
                                ("GET", f"/api/v1/knowledge/{other_id}/status", {}),
                                ("PUT", f"/api/v1/knowledge/{other_id}", {"json": {"title": "pwned title"}}),
                                ("DELETE", f"/api/v1/knowledge/{other_id}", {}),
                                ("DELETE", f"/api/v1/knowledge/{other_id}/permanent", {"json": {"confirmation": "SOP_ISO_B1"}})):
            r = c.request(method, url, headers=a, **kw)
            assert r.status_code == 404, (method, url, r.status_code, r.text)
        # Own item can still be moved only within the organization.
        own_id = next(i["item"]["id"] for i in mine["items"])
        assert c.put(f"/api/v1/knowledge/{own_id}", headers=a, json={"department_id": "dept_b"}).status_code == 404

        owd = open(OWD_DIR, "rb").read()
        up = c.post("/api/v1/knowledge/upload", headers=a, data={"department_id": "dept_b", "title": "Injected SOP"},
                    files={"file": ("x.md", owd, "text/markdown")})
        assert up.status_code == 404
        # A document that declares another department than the one selected is refused.
        mismatch = c.post("/api/v1/knowledge/upload", headers=a, data={"department_id": "dept_a", "title": "Mismatch SOP"},
                          files={"file": ("x.md", owd.replace(b"dept_inbound", b"dept_b"), "text/markdown")})
        assert mismatch.status_code == 422 and mismatch.json()["detail"]["error_code"] == "DEPARTMENT_MISMATCH", mismatch.text

        # Reference documents: every department-addressed route is scoped.
        for method, url in (("GET", "/api/v1/knowledge/references?department_id=dept_b"),
                            ("GET", "/api/v1/knowledge/references/doc_x?department_id=dept_b"),
                            ("GET", "/api/v1/knowledge/references/doc_x/content?department_id=dept_b"),
                            ("POST", "/api/v1/knowledge/references/doc_x/approve?department_id=dept_b"),
                            ("POST", "/api/v1/knowledge/references/doc_x/archive?department_id=dept_b")):
            assert c.request(method, url, headers=a).status_code == 404, (method, url)
        ref = c.post("/api/v1/knowledge/references", headers=a, data={"department_id": "dept_b", "title": "Injected reference"},
                     files={"file": ("n.txt", b"Scan the seal before unloading.", "text/plain")})
        assert ref.status_code == 404
        # Same routes still work for the admin's own department (scope is not over-blocking).
        assert c.get("/api/v1/knowledge/references?department_id=dept_a", headers=a).status_code == 200
