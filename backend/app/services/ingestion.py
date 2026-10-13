"""Bounded, department-owned document source storage in PostgreSQL BYTEA.

References and validated OWD markdown share the same durable object table.
Never writes local permanent files or calls Snowflake PUT/REMOVE.
"""
from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path
from typing import Optional
from uuid import uuid4

from fastapi import UploadFile, HTTPException, status

from app.core.config import settings
from app.core.database import get_postgres_connection
from app.exceptions import WorkMateException

ALLOWED_EXTENSIONS = frozenset({".md"})
MAX_FILE_SIZE_BYTES = 25 * 1024 * 1024
_OBJECT_URI = re.compile(r"^pgobj:([0-9a-f]{32})$")


class IngestionService:
    @staticmethod
    def validate_upload(file: UploadFile) -> bool:
        extension = Path(file.filename or "").suffix.lower()
        if extension not in ALLOWED_EXTENSIONS:
            raise HTTPException(status_code=400, detail={
                "error_code": "INVALID_FILE_TYPE",
                "message": "Only validated OWD Markdown (.md) is publishable.",
                "details": None,
            })
        file.file.seek(0, os.SEEK_END)
        size = file.file.tell()
        file.file.seek(0)
        if size > MAX_FILE_SIZE_BYTES:
            raise HTTPException(status_code=400, detail={
                "error_code": "FILE_TOO_LARGE",
                "message": "Document exceeds the 25 MB maximum.",
                "details": None,
            })
        return True

    validate_document = validate_upload

    @staticmethod
    def stage_file(
        raw_bytes: bytes, filename: str, stage_prefix: str,
        stage_name: Optional[str] = None,
        allowed_extensions: Optional[frozenset[str]] = None,
        *, department_id: Optional[str] = None,
    ) -> str:
        del stage_name  # Historical API compatibility; PostgreSQL has no stages.
        allowed = allowed_extensions or ALLOWED_EXTENSIONS
        safe_name = Path(filename.replace("\\", "/")).name
        if Path(safe_name).suffix.lower() not in allowed:
            raise WorkMateException(message="Uploaded source type is not allowed.")
        if not raw_bytes or len(raw_bytes) > min(MAX_FILE_SIZE_BYTES, settings.SOURCE_OBJECT_MAX_BYTES):
            raise WorkMateException(message="Document is empty or exceeds 25 MB.")
        if not re.fullmatch(r"[A-Za-z0-9_.-]{1,255}", safe_name):
            raise WorkMateException(message="Unsafe source filename.")
        if not department_id or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", department_id):
            raise WorkMateException(message="Valid department scope is required for file storage.")
        if not stage_prefix or len(stage_prefix) > 512:
            raise WorkMateException(message="Invalid source namespace.")
        object_id = uuid4().hex
        with get_postgres_connection() as conn:
            with conn.cursor() as cur:
                if settings.POSTGRES_RLS_REFERENCES:
                    cur.execute("BEGIN")
                    cur.execute("SELECT set_config('workmate.department_id', %s, true)", (department_id,))
                cur.execute(
                    """INSERT INTO shared.source_objects
                       (id, department_id, filename, sha256_hash, content)
                       VALUES (%s, %s, %s, %s, %s)""",
                    (object_id, department_id, safe_name, hashlib.sha256(raw_bytes).hexdigest(), raw_bytes),
                )
                if settings.POSTGRES_RLS_REFERENCES:
                    cur.execute("COMMIT")
        return f"pgobj:{object_id}"

    @staticmethod
    def stage_reference_file(raw_bytes: bytes, filename: str, department_id: str, document_id: str) -> str:
        from app.services.document_extraction import SUPPORTED_DOCUMENT_EXTENSIONS
        if not re.fullmatch(r"[0-9a-f]{32}", document_id):
            raise WorkMateException(message="Invalid reference identifier.")
        return IngestionService.stage_file(
            raw_bytes, filename, f"reference/{department_id}/{document_id}",
            allowed_extensions=SUPPORTED_DOCUMENT_EXTENSIONS,
            department_id=department_id,
        )

    stage_file_in_snowflake = stage_file  # Deprecated name, PostgreSQL-only implementation.

    @staticmethod
    def remove_staged_files(stage_file_uris: list[str], *, department_id: Optional[str] = None) -> int:
        ids: list[str] = []
        for uri in stage_file_uris:
            match = _OBJECT_URI.fullmatch(uri)
            if match is None:
                raise WorkMateException(message="Unrecognized source URI; refusing deletion.")
            ids.append(match.group(1))
        if not ids:
            return 0
        if settings.POSTGRES_RLS_REFERENCES and not department_id:
            raise WorkMateException(message="Department scope required to delete source objects.")
        with get_postgres_connection() as conn:
            with conn.cursor() as cur:
                if settings.POSTGRES_RLS_REFERENCES:
                    cur.execute("BEGIN")
                    cur.execute("SELECT set_config('workmate.department_id', %s, true)", (department_id,))
                cur.execute(
                    "DELETE FROM shared.source_objects WHERE id = ANY(%s)"
                    + (" AND department_id = %s" if department_id else ""),
                    (list(dict.fromkeys(ids)), department_id) if department_id
                    else (list(dict.fromkeys(ids)),),
                )
                count = cur.rowcount
                if settings.POSTGRES_RLS_REFERENCES:
                    cur.execute("COMMIT")
                return count
