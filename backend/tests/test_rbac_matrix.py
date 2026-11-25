"""Observed role matrix for every API operation, pinned as a golden file.

Each OpenAPI operation is called anonymously and with an admin, manager and
employee token (DB re-validation disabled, fake identities, empty JSON body).
"denied" means 401/403 from the auth/role dependency; anything else means the
role reached the handler (which may then reject the fake data with 4xx/5xx).
The result is compared with backend/tests/golden/rbac_matrix.json, so a route
that gains or loses a guard fails this test until the change is reviewed and
the golden file is regenerated:  UPDATE_RBAC_GOLDEN=1 pytest backend/tests/test_rbac_matrix.py

This proves the role guard exists on each route; tenant scoping inside the
handlers is covered by test_org_admin_postgres.py.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.security import create_access_token
from app.main import app

GOLDEN = Path(__file__).parent / "golden" / "rbac_matrix.json"
PUBLIC = {"/", "/ready", "/health", "/health/ai", "/api/v1/auth/login", "/api/v1/auth/refresh",
          "/api/v1/auth/revoke", "/api/v1/auth/token/redeem"}


def observe() -> dict:
    settings.AUTH_REVALIDATE_DB = False
    client = TestClient(app, raise_server_exceptions=False)
    tokens = {r: {"Authorization": "Bearer " + create_access_token("user_x", r, "dept_x")}
              for r in ("admin", "manager", "employee")}
    matrix = {}
    for path, ops in sorted(app.openapi()["paths"].items()):
        if path in PUBLIC or path.startswith(("/docs", "/redoc", "/openapi")):
            continue
        url = re.sub(r"\{[^}]+\}", "x", path)
        for method in sorted(m for m in ops if m in {"get", "post", "put", "patch", "delete"}):
            row = {"anonymous": client.request(method, url).status_code in (401, 403) and "denied" or "OPEN"}
            for role, hdr in tokens.items():
                code = client.request(method, url, headers=hdr, json={} if method != "get" else None).status_code
                row[role] = "denied" if code in (401, 403) else "allowed"
            matrix[f"{method.upper()} {path}"] = row
    return matrix


def test_rbac_matrix_matches_golden_and_no_anonymous_access():
    observed = observe()
    assert len(observed) >= 60
    assert all(r["anonymous"] == "denied" for r in observed.values()), \
        [k for k, r in observed.items() if r["anonymous"] != "denied"]
    if os.environ.get("UPDATE_RBAC_GOLDEN") == "1":
        GOLDEN.write_text(json.dumps(observed, indent=1, sort_keys=True), encoding="utf-8")
    expected = json.loads(GOLDEN.read_text(encoding="utf-8"))
    changed = {k: (expected.get(k), observed.get(k)) for k in set(expected) | set(observed)
               if expected.get(k) != observed.get(k)}
    assert not changed, changed


def test_admin_only_surfaces_are_closed_to_other_roles():
    observed = json.loads(GOLDEN.read_text(encoding="utf-8"))
    must_be_admin_only = [k for k in observed if "/admin/" in k or k.startswith(("POST /api/v1/knowledge", "DELETE /api/v1/knowledge"))]
    assert must_be_admin_only
    for key in must_be_admin_only:
        row = observed[key]
        assert row["employee"] == "denied", key
        if "/admin/" in key:
            assert row["manager"] == "denied", key
