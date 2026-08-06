"""Standalone seed script: seeds departments, roles, and users into Snowflake."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.database import get_snowflake_connection
from app.core.security import hash_password

DEFAULT_PASSWORD = "Test1234!"
hashed_pw = hash_password(DEFAULT_PASSWORD)

SEED_DEPARTMENTS = [
    {"id": "dept_admin",   "name": "Executive Administration"},
    {"id": "dept_ops",     "name": "Operations and Logistics"},
    {"id": "dept_inbound", "name": "Inbound Receiving"},
    {"id": "dept_eng",     "name": "Engineering and Tech"},
]

SEED_ROLES = [
    {"id": "role_admin",    "name": "admin",    "permissions": '{"all": true}'},
    {"id": "role_manager",  "name": "manager",  "permissions": '{"view_analytics": true, "manage_sops": true}'},
    {"id": "role_employee", "name": "employee", "permissions": '{"use_copilot": true}'},
]

SEED_USERS = [
    {"id": "usr_admin001", "email": "admin@workmate.ai",    "department_id": "dept_admin",   "role_id": "role_admin",    "role_name": "admin"},
    {"id": "usr_mgr001",   "email": "manager@workmate.ai",  "department_id": "dept_ops",     "role_id": "role_manager",  "role_name": "manager"},
    {"id": "usr_emp001",   "email": "employee@workmate.ai", "department_id": "dept_inbound", "role_id": "role_employee", "role_name": "employee"},
]


def run():
    print("=" * 60)
    print("  WorkMate AI - Seeding Login Credentials into Snowflake")
    print("=" * 60)

    try:
        with get_snowflake_connection() as conn:
            with conn.cursor() as cur:

                print("\n[1/3] Seeding Departments...")
                for dept in SEED_DEPARTMENTS:
                    cur.execute(
                        """MERGE INTO departments t
                           USING (SELECT %s AS id, %s AS name) s ON t.id = s.id
                           WHEN MATCHED THEN UPDATE SET name = s.name
                           WHEN NOT MATCHED THEN INSERT (id, name) VALUES (s.id, s.name)""",
                        (dept["id"], dept["name"]),
                    )
                    print(f"  [OK] {dept['name']} ({dept['id']})")

                print("\n[2/3] Seeding Roles...")
                for r in SEED_ROLES:
                    cur.execute(
                        """MERGE INTO roles t
                           USING (SELECT %s AS id, %s AS name, PARSE_JSON(%s) AS permission_set) s ON t.id = s.id
                           WHEN MATCHED THEN UPDATE SET name = s.name, permission_set = s.permission_set
                           WHEN NOT MATCHED THEN INSERT (id, name, permission_set) VALUES (s.id, s.name, s.permission_set)""",
                        (r["id"], r["name"], r["permissions"]),
                    )
                    print(f"  [OK] {r['name']} ({r['id']})")

                print("\n[3/3] Seeding Users + User Roles...")
                for u in SEED_USERS:
                    cur.execute(
                        """MERGE INTO users t
                           USING (SELECT %s AS id, %s AS email, %s AS hashed_password, %s AS department_id) s ON t.id = s.id
                           WHEN MATCHED THEN UPDATE SET email = s.email, hashed_password = s.hashed_password, department_id = s.department_id
                           WHEN NOT MATCHED THEN INSERT (id, email, hashed_password, department_id) VALUES (s.id, s.email, s.hashed_password, s.department_id)""",
                        (u["id"], u["email"], hashed_pw, u["department_id"]),
                    )
                    cur.execute(
                        """MERGE INTO user_roles t
                           USING (SELECT %s AS user_id, %s AS role_id) s ON t.user_id = s.user_id AND t.role_id = s.role_id
                           WHEN NOT MATCHED THEN INSERT (user_id, role_id) VALUES (s.user_id, s.role_id)""",
                        (u["id"], u["role_id"]),
                    )
                    print(f"  [OK] {u['email']}  role={u['role_name']}  dept={u['department_id']}")

        print("\n" + "=" * 65)
        print("  Seed Complete! Ready to log in.")
        print("=" * 65)
        print(f"  {'Role':<10} | {'Email':<25} | {'Password':<12} | Department")
        print(f"  {'-'*10}-+-{'-'*25}-+-{'-'*12}-+------------------")
        for u in SEED_USERS:
            print(f"  {u['role_name']:<10} | {u['email']:<25} | {DEFAULT_PASSWORD:<12} | {u['department_id']}")
        print("=" * 65)
        print("\n  Login at: http://localhost:3000/login")
        print()

    except Exception as exc:
        print(f"\n[ERROR] Seed failed: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    run()
