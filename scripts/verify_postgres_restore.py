"""Disposable PostgreSQL custom-format backup + restore acceptance check.

Creates a synthetic reference source, dumps the entire disposable CI database,
restores to a distinct temporary database, verifies metadata and BYTEA SHA-256.
Never runs against a remote host or production environment.
"""
from __future__ import annotations

import hashlib
import os
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

import psycopg


def verify() -> None:
    dsn = os.environ.get("DATABASE_URL", "")
    if os.environ.get("WORKMATE_BACKUP_SMOKE") != "1":
        raise RuntimeError("Explicit disposable backup test flag required")
    url = urlsplit(dsn)
    if url.scheme not in {"postgres", "postgresql"} or url.hostname not in {"localhost", "127.0.0.1"}:
        raise RuntimeError("Refusing backup/restore verification outside local CI")
    original_db = url.path.lstrip("/")
    if original_db != "workmate":
        raise RuntimeError("Backup smoke only runs against the disposable workmate CI DB")
    suffix = uuid4().hex[:10]
    temporary_db = "wm_restore_" + suffix
    dept = "restore_" + suffix
    payload = ("Receiving audit backup • नमूना " + suffix).encode()
    object_id = uuid4().hex
    expected_hash = hashlib.sha256(payload).hexdigest()
    def replace_db(db: str) -> str:
        return urlunsplit((url.scheme, url.netloc, "/" + db, "", ""))
    root_dsn = replace_db("postgres")
    restored_dsn = replace_db(temporary_db)
    try:
        with psycopg.connect(dsn, autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute("INSERT INTO security.departments (id,code,name) VALUES (%s,%s,%s)",
                            (dept, dept.upper(), "Restore smoke"))
                cur.execute("""INSERT INTO shared.source_objects
                    (id,department_id,filename,sha256_hash,content)
                    VALUES (%s,%s,%s,%s,%s)""",
                    (object_id,dept,"restore.bin",expected_hash,payload))
        with tempfile.TemporaryDirectory(prefix="wm_pgbackup_") as dirname:
            dump = Path(dirname) / "backup.dump"
            subprocess.run(["pg_dump", "--format=custom", "--no-owner", "--no-acl",
                            "--dbname", dsn, "--file", str(dump)],
                           check=True, timeout=60, capture_output=True)
            assert dump.stat().st_size > 5000
            with psycopg.connect(root_dsn, autocommit=True) as conn:
                with conn.cursor() as cur:
                    cur.execute(f'CREATE DATABASE "{temporary_db}"')
            subprocess.run(["pg_restore", "--no-owner", "--no-acl", "--exit-on-error",
                            "--dbname", restored_dsn, str(dump)],
                           check=True, timeout=90, capture_output=True)
            with psycopg.connect(restored_dsn) as restored:
                with restored.cursor() as cur:
                    cur.execute("""SELECT so.department_id, so.sha256_hash, so.content
                        FROM shared.source_objects so WHERE so.id=%s""", (object_id,))
                    row = cur.fetchone()
                    assert row is not None
                    assert row[0] == dept and row[1] == expected_hash
                    assert hashlib.sha256(bytes(row[2])).hexdigest() == expected_hash
                    cur.execute("SELECT 1 FROM security.departments WHERE id=%s", (dept,))
                    assert cur.fetchone() == (1,)
            print("DISPOSABLE POSTGRES BACKUP/RESTORE PASS: metadata, original source bytes, SHA-256 match.")
    finally:
        with psycopg.connect(root_dsn, autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname=%s", (temporary_db,))
                cur.execute(f'DROP DATABASE IF EXISTS "{temporary_db}"')
        with psycopg.connect(dsn, autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM shared.source_objects WHERE id=%s", (object_id,))
                cur.execute("DELETE FROM security.departments WHERE id=%s", (dept,))


if __name__ == "__main__":
    verify()
