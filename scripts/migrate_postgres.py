"""Run PostgreSQL DDL using a migration credential, never the runtime login.

In development and disposable CI, DATABASE_URL remains a supported input.
For APP_ENV=production or staging, MIGRATION_DATABASE_URL is mandatory and
must differ from DATABASE_URL. The application never invokes this at startup.
"""
from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlsplit

import psycopg

MIGRATIONS = Path(__file__).resolve().parents[1] / "backend" / "migrations" / "postgres"


def _identity(dsn: str) -> tuple[str, str, str]:
    parsed = urlsplit(dsn)
    if parsed.scheme not in ("postgresql", "postgres") or not parsed.hostname:
        raise ValueError("Migration requires a valid PostgreSQL URL")
    return (parsed.username or "", parsed.hostname, parsed.path)


def migrate(dsn: str) -> None:
    _identity(dsn)
    files = sorted(MIGRATIONS.glob("[0-9][0-9][0-9]_*.sql"))
    if not files:
        raise RuntimeError("No PostgreSQL migrations found")
    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cur:
            # All SQL files share one transaction; failed DDL is rolled back.
            for path in files:
                cur.execute(path.read_text(encoding="utf-8"), prepare=False)


def select_migration_url(env: dict[str, str]) -> str:
    mode = env.get("APP_ENV", "dev").strip().lower()
    managed = mode in ("staging", "prod", "production")
    dsn = env.get("MIGRATION_DATABASE_URL", "")
    runtime = env.get("DATABASE_URL", "")
    if managed:
        if not dsn or not runtime:
            raise ValueError("Staging/production requires both migration and runtime URLs")
        if _identity(dsn)[0] == _identity(runtime)[0]:
            raise ValueError("Migration and runtime PostgreSQL roles must have distinct login names")
        if _identity(dsn)[1:] != _identity(runtime)[1:]:
            raise ValueError("Migration/runtime URLs must target the same host and database")
    return dsn or runtime


if __name__ == "__main__":
    dsn = select_migration_url(dict(os.environ))
    if not dsn:
        raise SystemExit("Set MIGRATION_DATABASE_URL or development DATABASE_URL")
    migrate(dsn)
    print("PostgreSQL ordered migrations applied.")
