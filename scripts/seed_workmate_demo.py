"""Opt-in, idempotent local demo seeding. Never enable on staging or production.

Creates only queued work and demo accounts. No published/approved SOPs,
fabricated evidence, completed work or artificial analytics are created.
"""
from __future__ import annotations

import os
from urllib.parse import urlsplit
from uuid import uuid4


DEMO_USERS = (
    ("wm_demo_amira", "amira.demo@workmate.test", "Amira Khan", "employee", "wm_demo_employee"),
    ("wm_demo_ravi", "ravi.demo@workmate.test", "Ravi Patel", "employee", "wm_demo_employee"),
    ("wm_demo_lead", "lead.demo@workmate.test", "Taylor Morgan", "manager", "wm_demo_manager"),
)

DEMO_TASKS = (
    ("DEMO-GRN-2041", "Inspect inbound pallet seals", "receiving", "high",
     "Verify dock manifest against pallet labels; report broken seals.", "wm_demo_amira"),
    ("DEMO-GRN-2042", "Count carton quantities for receipt", "receiving", "standard",
     "Compare the received carton count with the documented quantity.", "wm_demo_ravi"),
    ("DEMO-PUT-3107", "Put away verified stock", "putaway", "standard",
     "Confirm the intended location before moving inspected stock.", "wm_demo_amira"),
    ("DEMO-PICK-4029", "Pick items for outbound order", "picking", "high",
     "Check order lines and hold any mismatched stock for supervisor review.", "wm_demo_ravi"),
    ("DEMO-CC-1180", "Cycle count aisle B3", "stock_count", "standard",
     "Record observed counts and flag differences; do not overwrite inventory.", "wm_demo_amira"),
    ("DEMO-DSP-7004", "Prepare dispatch manifest", "dispatch", "high",
     "Cross-check package labels and shipping manifest before dispatch.", None),
    ("DEMO-RET-2110", "Triage a returned carton", "other", "standard",
     "Inspect packaging and quarantine uncertain contents for review.", None),
)


def validate_demo_environment(env: dict[str, str]) -> tuple[str, str]:
    if env.get("WORKMATE_DEMO_SEED") != "1":
        raise RuntimeError("Set WORKMATE_DEMO_SEED=1 to explicitly opt in.")
    if env.get("APP_ENV", "").lower() not in ("dev", "development", "test"):
        raise RuntimeError("Demo seeding is restricted to APP_ENV=dev/development/test.")
    password = env.get("WORKMATE_DEMO_PASSWORD", "")
    if len(password) < 16:
        raise RuntimeError("WORKMATE_DEMO_PASSWORD must contain at least 16 characters.")
    dsn = env.get("DATABASE_URL", "")
    try:
        parsed = urlsplit(dsn)
        allowed = (
            parsed.scheme in ("postgres", "postgresql")
            and parsed.hostname in ("localhost", "127.0.0.1", "postgres")
            and parsed.path == "/workmate"
            and parsed.username == "workmate"
        )
    except ValueError:
        allowed = False
    if not allowed:
        raise RuntimeError("Demo seeding requires the standard local WorkMate PostgreSQL database.")
    department = env.get("WORKMATE_DEMO_DEPARTMENT", "warehouse").strip()
    if not department or len(department) > 64:
        raise RuntimeError("Invalid local demo department.")
    return password, department


def seed() -> None:
    password, department = validate_demo_environment(dict(os.environ))
    import psycopg
    from app.core.security import hash_password

    dsn = os.environ["DATABASE_URL"]
    created = 0
    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", ("wm-demo:" + department,))
            cur.execute("SELECT 1 FROM security.departments WHERE id=%s AND is_active", (department,))
            if cur.fetchone() is None:
                raise RuntimeError("Create the local Warehouse department/admin first.")
            cur.execute("""SELECT u.id FROM security.users u
                JOIN security.user_roles ur ON ur.user_id=u.id
                JOIN security.roles r ON r.id=ur.role_id
                WHERE u.department_id=%s AND u.status='active' AND LOWER(r.name)='admin'
                ORDER BY u.created_at LIMIT 1""", (department,))
            admin = cur.fetchone()
            if not admin:
                raise RuntimeError("Create an active local administrator before demo seeding.")
            actor = admin[0]

            for role_id, role in (("wm_demo_employee", "employee"), ("wm_demo_manager", "manager")):
                cur.execute("""INSERT INTO security.roles (id,name,permission_set)
                    VALUES (%s,%s,'{}'::jsonb) ON CONFLICT (id) DO NOTHING""", (role_id, role))

            password_hash = hash_password(password)
            for user_id, email, name, _, role_id in DEMO_USERS:
                cur.execute("""INSERT INTO security.users
                    (id,email,hashed_password,department_id,full_name,status)
                    VALUES (%s,%s,%s,%s,%s,'active')
                    ON CONFLICT (id) DO NOTHING""",
                    (user_id, email, password_hash, department, name))
                cur.execute("SELECT department_id FROM security.users WHERE id=%s", (user_id,))
                if cur.fetchone()[0] != department:
                    raise RuntimeError("Demo identity belongs to another department; refusing to alter it.")
                cur.execute("""INSERT INTO security.user_roles (user_id,role_id)
                    VALUES (%s,%s) ON CONFLICT DO NOTHING""", (user_id, role_id))

            for ref, title, work_type, priority, instructions, employee in DEMO_TASKS:
                cur.execute("""SELECT id FROM workmate_copilot.work_items
                    WHERE department_id=%s AND external_reference=%s LIMIT 1""", (department, ref))
                if cur.fetchone():
                    continue
                identifier = "wrk_" + uuid4().hex
                cur.execute("""INSERT INTO workmate_copilot.work_items
                    (id,department_id,created_by,assigned_to,external_reference,title,work_type,priority,instructions,status)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,'queued')""",
                    (identifier, department, actor, employee, ref, title, work_type, priority, instructions))
                cur.execute("""INSERT INTO workmate_copilot.work_item_events
                    (id,work_item_id,department_id,actor_id,action)
                    VALUES (%s,%s,%s,%s,'created')""", (uuid4().hex, identifier, department, actor))
                created += 1

    print(f"WorkMate local demo ready: {created} new queued tasks, {len(DEMO_USERS)} demo identities.")
    print("Demo user emails: " + ", ".join(user[1] for user in DEMO_USERS))
    print("Sign in with the password supplied via WORKMATE_DEMO_PASSWORD.")
    print("No approved SOP, completed work, evidence or analytics were fabricated.")


if __name__ == "__main__":
    seed()
