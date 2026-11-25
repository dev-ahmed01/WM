"""Regenerate docs/rbac-permission-matrix.md from the pinned golden matrix.

    python scripts/generate_rbac_doc.py
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
matrix = json.loads((ROOT / "backend/tests/golden/rbac_matrix.json").read_text(encoding="utf-8"))
mark = lambda v: "✔" if v == "allowed" else "—"
rows = ["| Operation | Admin | Manager | Employee |", "|---|---|---|---|"]
for key, row in sorted(matrix.items(), key=lambda kv: kv[0].split(" ", 1)[1]):
    rows.append(f"| `{key}` | {mark(row['admin'])} | {mark(row['manager'])} | {mark(row['employee'])} |")

text = f"""# RBAC Permission Matrix

Generated from `backend/tests/golden/rbac_matrix.json`, which `backend/tests/test_rbac_matrix.py` produces by calling
every API operation anonymously and with admin/manager/employee tokens. ✔ = the role reaches the handler; — = rejected
by the auth/role dependency (401/403). All {len(matrix)} operations deny anonymous callers.

**What this proves:** each route's role guard exists and matches this table; a change fails CI until the golden file is
regenerated and reviewed (`UPDATE_RBAC_GOLDEN=1`), then run `python scripts/generate_rbac_doc.py`.

**What it does not prove:** that a permitted role only sees its own organization's data. That is tested separately:
`test_org_admin_postgres.py` (employee admin, escalations), `test_tenant_knowledge_isolation_postgres.py`
(Knowledge Studio and reference documents, in a scratch database), and database RLS for reference documents. Row-level
security does **not** yet cover workflows, conversations, work items, exceptions, handovers or knowledge gaps; those rely
on application-layer organization/department filters.

Notes: `GET /api/v1/escalations`, `GET /api/v1/knowledge-gaps` and similar org-scoped routes may show — for every role
here because the probe uses a fake identity with no organization and the handler fails closed (403
`ORG_NOT_CONFIGURED`). `POST /api/v1/work/integrations/webhooks/{{source_id}}` is authenticated by HMAC signature,
not user role. Managers are scoped to their own department; admins to their organization.

""" + "\n".join(rows) + "\n"
(ROOT / "docs/rbac-permission-matrix.md").write_text(text, encoding="utf-8")
print("rows:", len(matrix))
