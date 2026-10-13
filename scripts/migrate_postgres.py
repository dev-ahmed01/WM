"""Apply audited PostgreSQL baseline atomically; never contact Snowflake."""
from __future__ import annotations

import os
from pathlib import Path

import psycopg

BASELINE = Path(__file__).resolve().parents[1] / "backend" / "migrations" / "postgres" / "001_baseline.sql"


def migrate(dsn: str) -> None:
    if not dsn.startswith(("postgresql://", "postgres://")):
        raise ValueError("DATABASE_URL must target PostgreSQL")
    source = BASELINE.read_text(encoding="utf-8")
    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cur:
            # A failed DDL statement rolls back the entire baseline.
            cur.execute(source, prepare=False)


if __name__ == "__main__":
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        raise SystemExit("Set DATABASE_URL. Refusing implicit production configuration.")
    migrate(dsn)
    print("PostgreSQL baseline applied successfully")
