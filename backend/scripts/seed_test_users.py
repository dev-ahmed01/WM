"""Development script to seed initial test users, roles, and departments in Snowflake."""

# Assumption: Script uses app.core.database connection settings and hashes password using app.core.security.

import sys
from pathlib import Path

# Add backend directory to sys.path so app module imports succeed when run directly
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.core.database import get_snowflake_connection
from app.core.security import hash_password

DEFAULT_PASSWORD = "Test1234!"

SEED_DEPARTMENTS = [
    {"id": "dept_admin", "code": "ADMIN", "name": "Executive Administration"},
    {"id": "dept_ops", "code": "OPS", "name": "Operations & Logistics"},
    {"id": "dept_inbound", "code": "INBOUND", "name": "Inbound Operations"},
]

SEED_ROLES = [
    {"id": "role_admin", "name": "admin", "permissions": '{"all": true}'},
    {"id": "role_manager", "name": "manager", "permissions": '{"view_analytics": true, "manage_sops": true}'},
    {"id": "role_employee", "name": "employee", "permissions": '{"use_copilot": true}'},
]

SEED_USERS = [
    {
        "id": "usr_admin001",
        "email": "admin@workmate.ai",
        "department_id": "dept_admin",
        "role_id": "role_admin",
        "role_name": "admin",
    },
    {
        "id": "usr_mgr001",
        "email": "manager@workmate.ai",
        "department_id": "dept_ops",
        "role_id": "role_manager",
        "role_name": "manager",
    },
    {
        "id": "usr_emp001",
        "email": "employee@workmate.ai",
        # Keep the demo employee in a migration-backed department that owns
        # seeded OWD content, so strict retrieval scoping can return guidance.
        "department_id": "dept_ops",
        "role_id": "role_employee",
        "role_name": "employee",
    },
    {
        "id": "usr_inbound001",
        "email": "inbound.employee@workmate.ai",
        "department_id": "dept_inbound",
        "role_id": "role_employee",
        "role_name": "employee",
    },
]


def seed_database():
    """Seeds departments, roles, users, and user_roles in Snowflake."""
    print("=" * 60)
    print("  WorkMate AI — Seeding Local Test Users into Snowflake")
    print("=" * 60)

    hashed_pw = hash_password(DEFAULT_PASSWORD)

    try:
        with get_snowflake_connection() as conn:
            with conn.cursor() as cur:
                # 1. Seed Departments
                print("\n[1/4] Seeding Departments...")
                for dept in SEED_DEPARTMENTS:
                    query = """
                        MERGE INTO SECURITY.departments target
                        USING (SELECT %s AS id, %s AS code, %s AS name) src
                        ON target.id = src.id
                        WHEN MATCHED THEN UPDATE SET code = src.code, name = src.name
                        WHEN NOT MATCHED THEN INSERT (id, code, name) VALUES (src.id, src.code, src.name)
                    """
                    cur.execute(query, (dept["id"], dept["code"], dept["name"]))
                    print(f"  [OK] Department: {dept['name']} ({dept['id']})")
                
                # 2. Seed Roles
                print("\n[2/4] Seeding Roles...")
                for r in SEED_ROLES:
                    query = """
                        MERGE INTO SECURITY.roles target
                        USING (SELECT %s AS id, %s AS name, PARSE_JSON(%s) AS permission_set) src
                        ON target.id = src.id
                        WHEN MATCHED THEN UPDATE SET name = src.name, permission_set = src.permission_set
                        WHEN NOT MATCHED THEN INSERT (id, name, permission_set) VALUES (src.id, src.name, src.permission_set)
                    """
                    cur.execute(query, (r["id"], r["name"], r["permissions"]))
                    print(f"  [OK] Role: {r['name']} ({r['id']})")

                # 3. Seed Users & User Roles
                print("\n[3/4] Seeding Users and User-Roles...")
                for u in SEED_USERS:
                    user_query = """
                        MERGE INTO SECURITY.users target
                        USING (SELECT %s AS id, %s AS email, %s AS hashed_password, %s AS department_id) src
                        ON target.id = src.id
                        WHEN MATCHED THEN UPDATE SET email = src.email, hashed_password = src.hashed_password, department_id = src.department_id
                        WHEN NOT MATCHED THEN INSERT (id, email, hashed_password, department_id) VALUES (src.id, src.email, src.hashed_password, src.department_id)
                    """
                    cur.execute(user_query, (u["id"], u["email"], hashed_pw, u["department_id"]))

                    user_role_query = """
                        MERGE INTO SECURITY.user_roles target
                        USING (SELECT %s AS user_id, %s AS role_id) src
                        ON target.user_id = src.user_id AND target.role_id = src.role_id
                        WHEN NOT MATCHED THEN INSERT (user_id, role_id) VALUES (src.user_id, src.role_id)
                    """
                    cur.execute(user_role_query, (u["id"], u["role_id"]))
                    print(f"  [OK] User: {u['email']} | Role: {u['role_name']} | Dept: {u['department_id']}")

        print("\n[4/4] Seed Complete! Test credentials ready:\n")
        print("-" * 65)
        print(f"{'Role':<12} | {'Email':<24} | {'Password':<12} | {'Dept ID':<10}")
        print("-" * 65)
        for u in SEED_USERS:
            print(f"{u['role_name']:<12} | {u['email']:<24} | {DEFAULT_PASSWORD:<12} | {u['department_id']:<10}")
        print("-" * 65)
        print("\nNote: Run scripts/deploy_owd_schema.py before seeding users.")

    except Exception as exc:
        print(f"\n❌ Error seeding test users in Snowflake: {str(exc)}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    seed_database()
