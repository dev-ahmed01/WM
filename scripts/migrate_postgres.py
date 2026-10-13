"""Apply audited PostgreSQL baseline atomically; never contact Snowflake."""
from __future__ import annotations

import os
from pathlib import Path

import psycopg

MIGRATIONS = Path(__file__).resolve().parents[1] / "backend" / "migrations" / "postgres"


def migrate(dsn: str) -> None:
    if not dsn.startswith(("postgresql://", "postgres://")):
        raise ValueError("DATABASE_URL must target PostgreSQL")
    files = sorted(MIGRATIONS.glob("[0-9][0-9][0-9]_*.sql"))
    if not files:
        raise RuntimeError("No PostgreSQL migrations found")
    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cur:
            # One transaction for all migrations; failure never leaves half a schema.
            for path in files:
                cur.execute(path.read_text(encoding="utf-8"), prepare=False)


if __name__ == "__main__":
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        raise SystemExit("Set DATABASE_URL. Refusing implicit production configuration.")
    migrate(dsn)
    print("PostgreSQL schema and analytics views applied successfully")
