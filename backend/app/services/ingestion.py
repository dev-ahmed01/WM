"""Knowledge Ingestion Service.

Handles OWD Markdown upload validation and unique Snowflake staging.
"""

import os
import tempfile
import logging
import re
from pathlib import Path
from typing import Optional
from fastapi import UploadFile, HTTPException, status

from app.core.config import settings
from app.core.database import get_snowflake_connection
from app.exceptions import WorkMateException

ingestion_logger = logging.getLogger("ingestion_jobs")

ALLOWED_EXTENSIONS = {".md"}
MAX_FILE_SIZE_BYTES = 25 * 1024 * 1024  # 25 MB


class IngestionService:
    """Core service for managing document upload validation and staging."""

    @staticmethod
    def validate_upload(file: UploadFile) -> bool:
        """Validates document file extension and size limit (<= 25MB)."""
        filename = file.filename or ""
        ext = os.path.splitext(filename)[1].lower()

        if ext not in ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error_code": "INVALID_FILE_TYPE",
                    "message": "Only OWD Markdown (.md) files are supported by the deterministic ingestion pipeline.",
                    "details": None,
                },
            )

        file.file.seek(0, os.SEEK_END)
        size_bytes = file.file.tell()
        file.file.seek(0)

        if size_bytes > MAX_FILE_SIZE_BYTES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error_code": "FILE_TOO_LARGE",
                    "message": f"File size exceeds 25 MB limit (Uploaded size: {size_bytes / (1024*1024):.2f} MB)",
                    "details": None,
                },
            )

        return True

    validate_document = validate_upload

    @staticmethod
    def stage_file(raw_bytes: bytes, filename: str, stage_prefix: str, stage_name: Optional[str] = None) -> str:
        """Upload validated bytes to a unique, version-scoped Snowflake stage path."""
        stage_name = stage_name or settings.SNOWFLAKE_STAGE_NAME
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_$]*", stage_name):
            raise WorkMateException(message="Invalid Snowflake stage identifier.")
        safe_prefix = "/".join(
            part for part in (re.sub(r"[^A-Za-z0-9._-]", "_", p) for p in stage_prefix.split("/")) if part
        )
        if not safe_prefix:
            raise WorkMateException(message="Invalid Snowflake stage prefix.")
        sanitized_filename = re.sub(r"[^A-Za-z0-9._-]", "_", Path(filename).name)
        if not sanitized_filename.lower().endswith(".md"):
            raise WorkMateException(message="Staged OWD source must have a .md extension.")

        try:
            with tempfile.TemporaryDirectory(prefix="workmate_owd_") as temp_dir:
                temp_path = Path(temp_dir) / sanitized_filename
                temp_path.write_bytes(raw_bytes)
                snowflake_path = f"@{stage_name}/{safe_prefix}/{sanitized_filename}"
                formatted_path = temp_path.absolute().as_posix()
                if os.name == 'nt' and not formatted_path.startswith('/'):
                    file_uri = f"file:///{formatted_path}"
                else:
                    file_uri = f"file://{formatted_path}"
                put_query = f"PUT '{file_uri}' @{stage_name}/{safe_prefix} AUTO_COMPRESS=FALSE OVERWRITE=FALSE"

                ingestion_logger.info("Staging validated OWD source at %s", snowflake_path)
                with get_snowflake_connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute(put_query)
                        put_result = cur.fetchone()
                        if put_result is None:
                            raise WorkMateException(message="Snowflake PUT returned no upload result.")
                        # Snowflake PUT returns status in column 7. Avoid a second
                        # network round-trip through LIST for every uploaded SOP.
                        if len(put_result) > 6 and str(put_result[6]).upper() not in {
                            "UPLOADED",
                            "SKIPPED",
                        }:
                            raise WorkMateException(
                                message=f"Snowflake PUT failed with status '{put_result[6]}'."
                            )

            return snowflake_path
        except Exception as exc:
            ingestion_logger.error(f"Failed to stage file in Snowflake: {str(exc)}")
            raise WorkMateException(message=f"Failed to stage document in Snowflake: {str(exc)}") from exc

    stage_file_in_snowflake = stage_file

    @staticmethod
    def remove_staged_files(stage_file_uris: list[str]) -> int:
        """Remove exact workflow source paths after their database transaction commits."""
        unique_uris = list(dict.fromkeys(uri.strip() for uri in stage_file_uris if uri.strip()))
        for stage_uri in unique_uris:
            if not re.fullmatch(
                r"@[A-Za-z_][A-Za-z0-9_$]*(?:/[A-Za-z0-9._-]+)+",
                stage_uri,
            ):
                raise WorkMateException(message="Invalid staged SOP path; file cleanup refused.")

        removed_count = 0
        try:
            with get_snowflake_connection() as conn:
                with conn.cursor() as cur:
                    for stage_uri in unique_uris:
                        cur.execute(f"REMOVE {stage_uri}")
                        removed_count += len(cur.fetchall())
            return removed_count
        except WorkMateException:
            raise
        except Exception as exc:
            ingestion_logger.error("Failed to remove staged SOP files: %s", type(exc).__name__)
            raise WorkMateException(message="Workflow records were deleted, but staged file cleanup failed.") from exc
