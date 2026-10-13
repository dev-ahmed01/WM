"""Encrypted PostgreSQL logical snapshot to an operator-mounted private directory.

Requires pg_dump and age. Writes only .age ciphertext; plaintext stays in pipe.
This is an on-host staging backup, not proof of off-host recovery or PITR.
"""
from __future__ import annotations

import os
import re
import subprocess
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urlsplit


def backup(dsn: str, recipient: str, directory: Path, retention_days: int) -> Path:
    parsed = urlsplit(dsn)
    if parsed.scheme not in {"postgresql", "postgres"} or not parsed.hostname:
        raise ValueError("BACKUP_DATABASE_URL must be a PostgreSQL connection URL")
    if not re.fullmatch(r"age1[023456789acdefghjklmnpqrstuvwxyz]{40,120}", recipient):
        raise ValueError("BACKUP_AGE_RECIPIENT must be a valid age public recipient")
    if not 1 <= retention_days <= 90:
        raise ValueError("Backup retention must be between 1 and 90 days")
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(directory, 0o700)
    filename = datetime.now(timezone.utc).strftime("wm-%Y%m%dT%H%M%SZ") + ".dump.age"
    final = directory / filename
    if final.exists():
        raise FileExistsError("A backup already exists for this second")
    fd, temporary = tempfile.mkstemp(dir=directory, prefix=".pending-", suffix=".age")
    os.close(fd)
    try:
        dump = subprocess.Popen(
            ["pg_dump", "--format=custom", "--no-owner", "--no-acl", "--dbname", dsn],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        assert dump.stdout is not None
        try:
            encrypt = subprocess.run(
                ["age", "--encrypt", "--recipient", recipient, "--output", temporary],
                stdin=dump.stdout, capture_output=True, check=False, timeout=180,
            )
        finally:
            dump.stdout.close()
        stderr = dump.stderr.read(8192) if dump.stderr is not None else b""
        dump_status = dump.wait(timeout=60)
        # Never print stderr: pg_dump can include hostnames and DB identifiers.
        if dump_status != 0 or encrypt.returncode != 0 or os.path.getsize(temporary) == 0:
            raise RuntimeError("PostgreSQL dump or encryption failed (no snapshot published)")
        os.chmod(temporary, 0o600)
        os.rename(temporary, final)
        cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
        for old in directory.glob("wm-*.dump.age"):
            if old == final or old.is_symlink():
                continue
            if datetime.fromtimestamp(old.stat().st_mtime, timezone.utc) < cutoff:
                old.unlink()
        return final
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


if __name__ == "__main__":
    url = os.environ.get("BACKUP_DATABASE_URL", "")
    recipient = os.environ.get("BACKUP_AGE_RECIPIENT", "")
    target = os.environ.get("BACKUP_DIRECTORY", "/var/backups/workmate")
    days = int(os.environ.get("BACKUP_RETENTION_DAYS", "7"))
    if not url or not recipient:
        raise SystemExit("Missing backup database URL or age public recipient")
    result = backup(url, recipient, Path(target), days)
    print("Encrypted PostgreSQL backup created:", result.name)
