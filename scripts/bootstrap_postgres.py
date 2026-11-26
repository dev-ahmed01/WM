"""One-time controlled administrator provisioning on PostgreSQL.

Required: DATABASE_URL, BOOTSTRAP_ADMIN_EMAIL, BOOTSTRAP_ADMIN_PASSWORD,
BOOTSTRAP_DEPARTMENT_ID, BOOTSTRAP_DEPARTMENT_NAME.
Optional: BOOTSTRAP_ORGANIZATION_NAME (defaults to the department name), BOOTSTRAP_WAREHOUSE_NAME.
The first administrator is placed in a real organization (required for every admin screen: employee
management, knowledge scope, approvals). Do not run this on every app startup; values are not printed.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.core.database import get_postgres_connection
from app.core.security import hash_password


def bootstrap() -> str:
    keys = (
        "BOOTSTRAP_ADMIN_EMAIL", "BOOTSTRAP_ADMIN_PASSWORD",
        "BOOTSTRAP_DEPARTMENT_ID", "BOOTSTRAP_DEPARTMENT_NAME",
    )
    data = {key: os.environ.get(key, "").strip() for key in keys}
    if not all(data.values()):
        raise ValueError("Required bootstrap administrator environment variables are missing.")
    email = data["BOOTSTRAP_ADMIN_EMAIL"].casefold()
    password = data["BOOTSTRAP_ADMIN_PASSWORD"]
    if len(password) < 16 or "@" not in email:
        raise ValueError("Administrator email or password does not meet requirements.")
    dept = data["BOOTSTRAP_DEPARTMENT_ID"]
    if not dept.replace("_", "").replace("-", "").isalnum() or len(dept) > 64:
        raise ValueError("Invalid department identifier.")
    with get_postgres_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("BEGIN")
            try:
                org_id = "org_" + dept.lower().replace("-", "_")[:56]
                org_name = os.environ.get("BOOTSTRAP_ORGANIZATION_NAME", "").strip() or data["BOOTSTRAP_DEPARTMENT_NAME"]
                cur.execute(
                    """INSERT INTO security.organizations (id,code,name) VALUES (%s,%s,%s)
                       ON CONFLICT (id) DO NOTHING""",
                    (org_id, org_id.upper()[:64], org_name[:255]),
                )
                warehouse_id = None
                warehouse_name = os.environ.get("BOOTSTRAP_WAREHOUSE_NAME", "").strip()
                if warehouse_name:
                    warehouse_id = "wh_" + dept.lower().replace("-", "_")[:56]
                    cur.execute(
                        """INSERT INTO security.warehouses (id,organization_id,code,name) VALUES (%s,%s,%s,%s)
                           ON CONFLICT (id) DO NOTHING""",
                        (warehouse_id, org_id, "MAIN", warehouse_name[:255]),
                    )
                cur.execute(
                    """INSERT INTO security.departments (id,code,name,organization_id)
                       VALUES (%s,%s,%s,%s)
                       ON CONFLICT (id) DO NOTHING""",
                    (dept, dept.upper(), data["BOOTSTRAP_DEPARTMENT_NAME"], org_id),
                )
                # A department created before organizations existed gets its owner organization now.
                cur.execute("UPDATE security.departments SET organization_id=%s WHERE id=%s AND organization_id IS NULL",
                            (org_id, dept))
                cur.execute("SELECT id FROM security.roles WHERE lower(name)='admin' ORDER BY (id='role_admin') DESC LIMIT 1")
                row = cur.fetchone()
                if row:
                    admin_role = row[0]
                else:
                    admin_role = "role_admin"
                    cur.execute(
                        """INSERT INTO security.roles (id,name,permission_set) VALUES ('role_admin','admin',%s::jsonb)""",
                        ('{"all": true}',),
                    )
                cur.execute("SELECT id FROM security.users WHERE lower(email)=%s", (email,))
                existing = cur.fetchone()
                if existing:
                    raise ValueError("Administrator email already exists; credentials will not be overwritten.")
                user_id = "usr_" + uuid4().hex[:24]
                cur.execute(
                    """INSERT INTO security.users
                       (id,email,hashed_password,department_id,full_name,status,warehouse_id)
                       VALUES (%s,%s,%s,%s,%s,'active',%s)""",
                    (user_id,email,hash_password(password),dept,"WorkMate Administrator",warehouse_id),
                )
                cur.execute(
                    """INSERT INTO security.user_roles (user_id,role_id)
                       VALUES (%s,%s)""", (user_id, admin_role),
                )
                cur.execute("COMMIT")
                return user_id
            except Exception:
                cur.execute("ROLLBACK")
                raise


if __name__ == "__main__":
    print("Administrator created:", bootstrap())
