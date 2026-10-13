"""Fail-closed preflight for non-owner staging/production PostgreSQL login."""
from __future__ import annotations

import os
from urllib.parse import urlsplit

import psycopg


def verify_runtime(dsn: str) -> dict[str, str]:
    parsed = urlsplit(dsn)
    if parsed.scheme not in ("postgresql", "postgres") or not parsed.hostname:
        raise ValueError("Expected a PostgreSQL runtime DSN")
    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT current_user, rolsuper, rolbypassrls, rolcreaterole, rolcreatedb
                   FROM pg_roles WHERE rolname=current_user""",
            )
            role, superuser, bypassrls, createrole, createdb = cur.fetchone()
            if any((superuser, bypassrls, createrole, createdb)):
                raise RuntimeError("Runtime PostgreSQL login holds unsafe administrative privileges")
            cur.execute(
                """SELECT EXISTS (
                     SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                     WHERE n.nspname IN ('knowledge_studio','shared','security','workmate_copilot')
                       AND c.relkind IN ('r','p') AND c.relowner = (
                          SELECT oid FROM pg_roles WHERE rolname=current_user
                       )
                   )""",
            )
            if cur.fetchone()[0]:
                raise RuntimeError("Runtime PostgreSQL login owns application tables")
            cur.execute("SELECT pg_has_role(current_user,'workmate_scoped_reader','MEMBER')")
            if not cur.fetchone()[0]:
                raise RuntimeError("Runtime role lacks grant for workmate_scoped_reader")
            cur.execute("SELECT has_schema_privilege(current_user, 'knowledge_studio', 'CREATE')")
            if cur.fetchone()[0]:
                raise RuntimeError("Runtime role can create schema objects")
            cur.execute("BEGIN")
            cur.execute("SET LOCAL ROLE workmate_scoped_reader")
            cur.execute("SELECT COUNT(*) FROM knowledge_studio.reference_documents")
            if cur.fetchone()[0] != 0:
                raise RuntimeError("Missing tenant context exposed reference documents")
            cur.execute("ROLLBACK")
    return {"role": role, "status": "verified_non_owner_rls"}


if __name__ == "__main__":
    dsn = os.environ.get("DATABASE_URL", "")
    if not dsn:
        raise SystemExit("DATABASE_URL required")
    result = verify_runtime(dsn)
    print("PostgreSQL runtime privilege checks passed:", result["role"])
