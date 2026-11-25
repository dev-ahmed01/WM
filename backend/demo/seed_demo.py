"""Idempotent local demo seeding for "WorkMate Demo Logistics".

    PYTHONPATH=backend python -m demo.seed_demo [--reset-passwords]

Safety: runs only when APP_ENV is dev/test/demo and DATABASE_URL points at
localhost. Passwords are random, written ONLY to the git-ignored local file
.demo-credentials.local.json (never printed, never committed). Re-running
creates nothing twice; existing SOPs are skipped, existing users keep their
passwords unless --reset-passwords is passed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import sys
from pathlib import Path
from urllib.parse import urlsplit

import psycopg

from app.core.config import settings
from app.core.security import hash_password
from demo.sop_catalog import AREAS, CATALOG, DEMO_DEPARTMENT_ID, DEMO_DEPARTMENT_NAME
from demo.sop_generator import render

ORG_ID, ORG_CODE, ORG_NAME = "org_demo_logistics", "DEMO-LOGISTICS", "WorkMate Demo Logistics (DEMONSTRATION DATA)"
WAREHOUSES = (("wh_demo_hyd", "HYD", "Hyderabad Fulfilment Centre (demo)"),
              ("wh_demo_pun", "PUN", "Pune Fulfilment Centre (demo)"))
CREDENTIALS_FILE = Path(__file__).resolve().parents[2] / ".demo-credentials.local.json"

# (user id, display name, role, job profile code, warehouse index, preferred language)
USERS = (
    ("demo_admin", "Demo Administrator", "admin", None, 0, "en"),
    ("demo_manager_hyd", "Demo Manager Hyderabad", "manager", None, 0, "en"),
    ("demo_manager_pun", "Demo Manager Pune", "manager", None, 1, "en"),
    ("demo_receiving", "Demo Receiving Associate", "employee", "RECEIVING_ASSOCIATE", 0, "en"),
    ("demo_picker", "Demo Picker", "employee", "PICKER", 0, "hinglish"),
    ("demo_packer", "Demo Packer", "employee", "PACKER", 0, "hi"),
    ("demo_dispatch", "Demo Dispatch Associate", "employee", "DISPATCH_ASSOCIATE", 0, "en"),
    ("demo_inventory", "Demo Inventory Associate", "employee", "INVENTORY_ASSOCIATE", 0, "en"),
    ("demo_quality", "Demo Quality Inspector", "employee", "QUALITY_INSPECTOR", 1, "en"),
    ("demo_mhe", "Demo Material Handler", "employee", "MATERIAL_HANDLING", 1, "hi"),
    ("demo_returns", "Demo Returns Associate", "employee", "RETURNS_ASSOCIATE", 1, "en"),
    ("demo_maintenance", "Demo Maintenance Associate", "employee", "MAINTENANCE_ASSOCIATE", 1, "en"),
    ("demo_general", "Demo General Employee", "employee", "GENERAL_EMPLOYEE", 1, "hinglish"),
)


def guard(dsn: str) -> None:
    host = urlsplit(dsn).hostname or ""
    env = os.environ.get("APP_ENV", "dev").lower()
    if env not in {"dev", "development", "test", "demo"} or host not in {"localhost", "127.0.0.1", "::1"}:
        raise SystemExit("Refusing to seed demo data: needs APP_ENV=dev|test|demo and a localhost DATABASE_URL.")


def _role_id(cur, role: str) -> str:
    cur.execute("SELECT id FROM security.roles WHERE LOWER(name)=%s ORDER BY (id=%s) DESC LIMIT 1", (role, f"role_{role}"))
    return cur.fetchone()[0]


def seed_structure_and_users(dsn: str, reset_passwords: bool) -> dict:
    creds = json.loads(CREDENTIALS_FILE.read_text()) if CREDENTIALS_FILE.exists() else {}
    created = 0
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute("INSERT INTO security.organizations (id,code,name,is_demo) VALUES (%s,%s,%s,TRUE) "
                    "ON CONFLICT (id) DO UPDATE SET name=EXCLUDED.name", (ORG_ID, ORG_CODE, ORG_NAME))
        for wid, code, name in WAREHOUSES:
            cur.execute("INSERT INTO security.warehouses (id,organization_id,code,name) VALUES (%s,%s,%s,%s) "
                        "ON CONFLICT (id) DO NOTHING", (wid, ORG_ID, code, name))
        cur.execute("INSERT INTO security.departments (id,code,name,organization_id) VALUES (%s,%s,%s,%s) "
                    "ON CONFLICT (id) DO NOTHING", (DEMO_DEPARTMENT_ID, "DEMO-OPS", DEMO_DEPARTMENT_NAME, ORG_ID))
        mgr_by_wh = {}
        for uid, name, role, profile, wh_i, lang in USERS:
            email = f"{uid}@demo.workmate.test"
            cur.execute("SELECT 1 FROM security.users WHERE id=%s", (uid,))
            exists = cur.fetchone() is not None
            if not exists or reset_passwords or uid not in creds:
                pw = secrets.token_urlsafe(14)
                creds[uid] = {"email": email, "password": pw, "role": role}
                pw_hash = hash_password(pw)
            else:
                pw_hash = None
            profile_id = None
            if profile:
                cur.execute("SELECT id FROM security.job_profiles WHERE code=%s", (profile,))
                profile_id = cur.fetchone()[0]
            wh = WAREHOUSES[wh_i][0]
            if not exists:
                cur.execute(
                    "INSERT INTO security.users (id,email,hashed_password,department_id,full_name,status,"
                    "job_profile_id,warehouse_id,preferred_language,is_demo) VALUES (%s,%s,%s,%s,%s,'active',%s,%s,%s,TRUE)",
                    (uid, email, pw_hash, DEMO_DEPARTMENT_ID, name, profile_id, wh, lang))
                cur.execute("INSERT INTO security.user_roles (user_id,role_id) VALUES (%s,%s) ON CONFLICT DO NOTHING",
                            (uid, _role_id(cur, role)))
                created += 1
            elif pw_hash:
                cur.execute("UPDATE security.users SET hashed_password=%s, status='active' WHERE id=%s", (pw_hash, uid))
            if role == "manager":
                mgr_by_wh[wh] = uid
        for uid, _n, role, _p, wh_i, _l in USERS:
            if role == "employee":
                cur.execute("UPDATE security.users SET supervisor_id=%s WHERE id=%s AND supervisor_id IS NULL",
                            (mgr_by_wh[WAREHOUSES[wh_i][0]], uid))
        conn.commit()
    CREDENTIALS_FILE.write_text(json.dumps(creds, indent=2))
    try:
        os.chmod(CREDENTIALS_FILE, 0o600)
    except OSError:
        pass
    return {"users_created": created, "credentials_file": str(CREDENTIALS_FILE)}


def publish_sops(dsn: str, republish: bool = False) -> dict:
    # Imported lazily so structure seeding does not need the whole app graph.
    from app.compiler.pipeline import OWDCompilerPipeline
    from app.services.ingestion import IngestionService

    published = skipped = failed = 0
    errors = []
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute("SELECT workflow_code FROM knowledge_studio.workflows WHERE department_id=%s", (DEMO_DEPARTMENT_ID,))
        existing = {r[0].upper().replace("-", "_") for r in cur.fetchall()}
    for sop in CATALOG:
        if not republish and sop.code.replace("-", "_") in existing:
            skipped += 1
            continue
        md = render(sop)
        raw = md.encode("utf-8")
        prefix = f"{sop.code}/v1/{hashlib.sha256(raw).hexdigest()[:12]}"
        uri = IngestionService.stage_file(raw, f"{sop.code}.md", prefix, department_id=DEMO_DEPARTMENT_ID)
        report = OWDCompilerPipeline.process_owd(
            markdown_text=md, title=sop.title, department_id=DEMO_DEPARTMENT_ID, user_id="demo_admin",
            stage_file_uri=uri, version_number=1, source_filename=f"{sop.code}.md")
        if report.get("compilation_status") == "SUCCESS" and report.get("deployment_status") != "FAILED":
            published += 1
        else:
            failed += 1
            errors.append((sop.code, report.get("compilation_status"), report.get("validation_errors", [])[:2]))
    return {"published": published, "skipped_existing": skipped, "failed": failed, "errors": errors}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--reset-passwords", action="store_true")
    ap.add_argument("--republish", action="store_true", help="re-compile existing demo SOPs in place (same version)")
    args = ap.parse_args()
    dsn = settings.DATABASE_URL
    guard(dsn)
    out = seed_structure_and_users(dsn, args.reset_passwords)
    out.update(publish_sops(dsn, args.republish))
    print(json.dumps(out, indent=2, default=str))
    return 1 if out["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
