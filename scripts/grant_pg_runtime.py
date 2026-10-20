"""Operator-only privilege provisioning for a pre-created PostgreSQL runtime login."""
import os
from urllib.parse import urlsplit

import psycopg
from psycopg import sql


def provision(migration_url: str, runtime_url: str) -> str:
    owner, runtime = urlsplit(migration_url), urlsplit(runtime_url)
    if owner.scheme not in ("postgres", "postgresql") or runtime.scheme not in ("postgres", "postgresql"):
        raise ValueError("Expected PostgreSQL URLs")
    if (owner.hostname, owner.port, owner.path) != (runtime.hostname, runtime.port, runtime.path):
        raise ValueError("Credentials must target the same database")
    user = runtime.username
    if not user or not owner.username or user == owner.username or user in ("postgres", "workmate_scoped_reader"):
        raise ValueError("Provide a separate non-privileged application login")
    with psycopg.connect(migration_url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT rolsuper, rolbypassrls, rolcreaterole, rolcreatedb, rolcanlogin "
                "FROM pg_roles WHERE rolname=%s", (user,),
            )
            flags = cur.fetchone()
            if not flags or flags != (False, False, False, False, True):
                raise ValueError("Create a non-superuser, non-BYPASSRLS LOGIN role with no DDL privileges")
            cur.execute(
                "SELECT 1 FROM pg_class WHERE relname='reference_documents' "
                "AND relnamespace='knowledge_studio'::regnamespace "
                "AND relowner=(SELECT oid FROM pg_roles WHERE rolname=%s)", (user,),
            )
            if cur.fetchone():
                raise ValueError("Runtime must not own protected tables")
            cur.execute(sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(
                sql.Identifier(owner.path.lstrip("/")), sql.Identifier(user)))
            for schema in ("security","knowledge_studio","workmate_copilot","intelligence_hub","shared"):
                cur.execute(sql.SQL("GRANT USAGE ON SCHEMA {} TO {}").format(
                    sql.Identifier(schema), sql.Identifier(user)))
                cur.execute(sql.SQL(
                    "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA {} TO {}"
                ).format(sql.Identifier(schema),sql.Identifier(user)))
            # Role membership is SET-only; no implicit inheritance of scoped reads.
            cur.execute(sql.SQL(
                "GRANT workmate_scoped_reader TO {} WITH INHERIT FALSE, SET TRUE"
            ).format(sql.Identifier(user)))
            tenant_predicate = "department_id = NULLIF(current_setting('workmate.department_id', true), '')"
            for schema, table, policy in [
                ("knowledge_studio","reference_documents","wm_runtime_document_scope"),
                ("knowledge_studio","reference_chunks","wm_runtime_chunk_scope"),
                ("shared","source_objects","wm_runtime_object_scope"),
            ]:
                cur.execute(
                    "SELECT 1 FROM pg_policies WHERE schemaname=%s AND tablename=%s AND policyname=%s",
                    (schema,table,policy),
                )
                template = (
                    "ALTER POLICY {} ON {}.{} TO {} USING ("+tenant_predicate+") WITH CHECK ("+tenant_predicate+")"
                    if cur.fetchone() else
                    "CREATE POLICY {} ON {}.{} FOR ALL TO {} USING ("+tenant_predicate+") WITH CHECK ("+tenant_predicate+")"
                )
                cur.execute(sql.SQL(template).format(
                    sql.Identifier(policy),sql.Identifier(schema),sql.Identifier(table),sql.Identifier(user),
                ))
    return user


if __name__ == "__main__":
    owner = os.getenv("MIGRATION_DATABASE_URL", "")
    runtime = os.getenv("DATABASE_URL", "")
    if not owner or not runtime:
        raise SystemExit("Set private MIGRATION_DATABASE_URL and DATABASE_URL")
    print("Scoped PostgreSQL runtime granted to:",provision(owner,runtime))
