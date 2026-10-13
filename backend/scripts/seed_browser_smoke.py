"""Seed disposable PostgreSQL-only browser users. Never run against production.

Required WORKMATE_BROWSER_SMOKE=1 and DATABASE_URL pointing at localhost.
Credentials are supplied through env, never written to tracked files or logs.
"""
from __future__ import annotations

import os

import psycopg

from app.core.security import hash_password

DEPARTMENTS = (
    ("e2e_ops", "QA OPS"),
    ("e2e_other", "QA OTHER"),
)
USERS = (
    ("e2e_admin", "e2e_admin@workmate.test", "e2e_ops", "e2e_role_admin"),
    ("e2e_employee", "e2e_employee@workmate.test", "e2e_ops", "e2e_role_employee"),
    ("e2e_other", "e2e_other@workmate.test", "e2e_other", "e2e_role_employee"),
    ("e2e_manager", "e2e_manager@workmate.test", "e2e_ops", "e2e_role_manager"),
)


def seed() -> None:
    dsn = os.environ.get("DATABASE_URL", "")
    password = os.environ.get("WORKMATE_E2E_PASSWORD", "")
    if (
        os.environ.get("WORKMATE_BROWSER_SMOKE") != "1"
        or os.environ.get("APP_ENV", "").lower() not in {"dev", "development", "test"}
        or not dsn.startswith(("postgresql://", "postgres://"))
        or "@localhost:" not in dsn
        or len(password) < 16
    ):
        raise RuntimeError("Browser seeds require explicit disposable local PostgreSQL and test credentials")
    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cur:
            for id_, code in DEPARTMENTS:
                cur.execute(
                    """INSERT INTO security.departments (id, code, name)
                       VALUES (%s,%s,%s) ON CONFLICT (id) DO NOTHING""",
                    (id_, code, code),
                )
            for role_id, name in (("e2e_role_admin", "admin"), ("e2e_role_employee", "employee"), ("e2e_role_manager", "manager")):
                cur.execute(
                    """INSERT INTO security.roles (id,name,permission_set)
                       VALUES (%s,%s,'{}'::jsonb) ON CONFLICT (id) DO NOTHING""",
                    (role_id, name),
                )
            for user_id, email, department, role_id in USERS:
                cur.execute(
                    """INSERT INTO security.users (id,email,hashed_password,department_id,status)
                       VALUES (%s,%s,%s,%s,'active') ON CONFLICT (id) DO UPDATE
                       SET hashed_password=EXCLUDED.hashed_password,
                           department_id=EXCLUDED.department_id, status='active'""",
                    (user_id, email, hash_password(password), department),
                )
                cur.execute(
                    """INSERT INTO security.user_roles (user_id,role_id)
                       VALUES (%s,%s) ON CONFLICT DO NOTHING""",
                    (user_id, role_id),
                )
    print("Disposable WorkMate browser identities seeded; passwords not logged.")


if __name__ == "__main__":
    seed()
