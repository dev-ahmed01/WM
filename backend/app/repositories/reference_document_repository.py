"""Department-isolated Snowflake repository for approved reference documents.

Reference material is not an OWD workflow and cannot mutate workflow state.
Every read and write carries an explicit department scope. This repository has
no LLM call; evidence is returned as verbatim excerpts with stable anchors.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from app.core.database import get_snowflake_connection


@dataclass(frozen=True)
class ReferenceChunk:
    id: str
    ordinal_index: int
    start_offset: int
    end_offset: int
    content: str
    sha256_hash: str


def chunk_reference_text(text: str, document_id: str, *, size: int = 1400, overlap: int = 160) -> list[ReferenceChunk]:
    """Stable exact-text spans, including offsets for human source verification."""
    if not text.strip() or size < 100 or overlap < 0 or overlap >= size:
        raise ValueError("Invalid text or chunk parameters")
    chunks: list[ReferenceChunk] = []
    start = 0
    while start < len(text):
        end = min(start + size, len(text))
        if end < len(text):
            # Avoid splitting inside a word when possible, without dropping text.
            boundary = text.rfind(" ", start + size // 2, end)
            if boundary > start:
                end = boundary + 1
        content = text[start:end]
        ordinal_index = len(chunks)
        chunks.append(ReferenceChunk(
            id=hashlib.sha256(f"{document_id}:{ordinal_index}".encode()).hexdigest()[:32],
            ordinal_index=ordinal_index,
            start_offset=start,
            end_offset=end,
            content=content,
            sha256_hash=hashlib.sha256(content.encode("utf-8")).hexdigest(),
        ))
        if end == len(text):
            break
        start = max(start + 1, end - overlap)
    return chunks


def new_reference_id() -> str:
    return uuid4().hex


def _serialize(row: Any) -> dict[str, Any]:
    return {
        "id": str(row[0]),
        "department_id": str(row[1]),
        "title": str(row[2]),
        "original_filename": str(row[3]),
        "file_type": str(row[4]),
        "status": str(row[5]),
        "extracted_characters": int(row[6]),
        "chunk_count": int(row[7]),
        "created_at": str(row[8]),
        "reviewed_at": str(row[9]) if row[9] else None,
    }


class ReferenceDocumentRepository:
    BASE_SELECT = """
        SELECT d.id, d.department_id, d.title, d.original_filename,
               d.file_extension, d.status, d.extracted_characters,
               (SELECT COUNT(*) FROM KNOWLEDGE_STUDIO.reference_chunks c WHERE c.document_id = d.id),
               d.created_at, d.reviewed_at
        FROM KNOWLEDGE_STUDIO.reference_documents d
    """

    @staticmethod
    def save_draft(
        *, document_id: str, department_id: str, title: str, filename: str,
        file_type: str, mime_type: str, stage_uri: str, raw: bytes,
        extracted_text: str, warnings: list[str], created_by: str,
    ) -> dict[str, Any]:
        chunks = chunk_reference_text(extracted_text, document_id)
        with get_snowflake_connection() as conn:
            with conn.cursor() as cur:
                try:
                    cur.execute("BEGIN")
                    cur.execute(
                        """INSERT INTO KNOWLEDGE_STUDIO.reference_documents
                        (id, department_id, title, original_filename, file_extension, mime_type,
                         stage_uri, sha256_hash, file_size_bytes, extracted_characters,
                         extraction_warnings, status, created_by)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'DRAFT',%s)""",
                        (
                            document_id, department_id, title, filename, file_type, mime_type,
                            stage_uri, hashlib.sha256(raw).hexdigest(), len(raw),
                            len(extracted_text), "\n".join(warnings)[:8192], created_by,
                        ),
                    )
                    cur.executemany(
                        """INSERT INTO KNOWLEDGE_STUDIO.reference_chunks
                        (id, document_id, department_id, ordinal_index, start_offset, end_offset,
                         content, sha256_hash) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
                        [
                            (c.id, document_id, department_id, c.ordinal_index, c.start_offset,
                             c.end_offset, c.content, c.sha256_hash)
                            for c in chunks
                        ],
                    )
                    cur.execute("COMMIT")
                except Exception:
                    cur.execute("ROLLBACK")
                    raise
        return {
            "id": document_id, "department_id": department_id, "title": title,
            "original_filename": filename, "file_type": file_type,
            "status": "DRAFT", "extracted_characters": len(extracted_text),
            "chunk_count": len(chunks),
        }

    @staticmethod
    def list_documents(department_id: str, *, limit: int = 50) -> list[dict[str, Any]]:
        with get_snowflake_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    ReferenceDocumentRepository.BASE_SELECT
                    + " WHERE d.department_id = %s ORDER BY d.created_at DESC LIMIT %s",
                    (department_id, limit),
                )
                return [_serialize(row) for row in cur.fetchall()]

    @staticmethod
    def get_document(document_id: str, department_id: str) -> dict[str, Any] | None:
        with get_snowflake_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    ReferenceDocumentRepository.BASE_SELECT
                    + " WHERE d.id = %s AND d.department_id = %s LIMIT 1",
                    (document_id, department_id),
                )
                row = cur.fetchone()
                return _serialize(row) if row else None

    @staticmethod
    def change_status(document_id: str, department_id: str, reviewer_id: str, *, action: str) -> bool:
        """Approval is explicit; archive is irreversible in the current version."""
        if action not in {"approve", "archive"}:
            raise ValueError("Invalid reference review action")
        from_status = "DRAFT" if action == "approve" else "APPROVED"
        to_status = "APPROVED" if action == "approve" else "ARCHIVED"
        with get_snowflake_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """UPDATE KNOWLEDGE_STUDIO.reference_documents
                    SET status = %s, reviewed_by = %s, reviewed_at = CURRENT_TIMESTAMP,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s AND department_id = %s AND status = %s""",
                    (to_status, reviewer_id, document_id, department_id, from_status),
                )
                count = cur.rowcount
                cur.execute("COMMIT")
                return bool(count)

    @staticmethod
    def read_chunks(document_id: str, department_id: str, *, limit: int = 50) -> list[dict[str, Any]]:
        """Administrators review source content before approving; no source Stage GET required."""
        with get_snowflake_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT c.id, c.ordinal_index, c.start_offset, c.end_offset, c.content
                    FROM KNOWLEDGE_STUDIO.reference_chunks c
                    JOIN KNOWLEDGE_STUDIO.reference_documents d ON c.document_id = d.id
                    WHERE c.document_id = %s AND c.department_id = %s AND d.department_id = %s
                    ORDER BY c.ordinal_index LIMIT %s""",
                    (document_id, department_id, department_id, limit),
                )
                return [{
                    "id": str(row[0]), "chunk_index": int(row[1]),
                    "start_offset": int(row[2]), "end_offset": int(row[3]),
                    "content": str(row[4]),
                } for row in cur.fetchall()]

    @staticmethod
    def list_approved_candidates(department_id: str, *, limit: int = 80) -> list[dict[str, Any]]:
        """Bounded, department-filtered semantic candidate pool.

        No vector index or cache may silently retain an archived source. Querying
        Snowflake on each request guarantees current approval status; the bounded
        pool is a recall limitation, not a claim of exhaustive semantic search.
        """
        if not department_id:
            return []
        limit = max(1, min(int(limit), 150))
        with get_snowflake_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT d.id, d.title, d.department_id, c.id, c.content,
                              c.ordinal_index, c.start_offset, c.end_offset, d.status
                       FROM KNOWLEDGE_STUDIO.reference_chunks c
                       JOIN KNOWLEDGE_STUDIO.reference_documents d ON d.id = c.document_id
                       WHERE d.department_id = %s AND c.department_id = %s
                         AND d.status = 'APPROVED'
                       ORDER BY d.updated_at DESC, c.id
                       LIMIT %s""",
                    (department_id, department_id, limit),
                )
                rows = cur.fetchall()
        return [
            {
                "document_id": str(row[0]), "document_title": str(row[1]),
                "department_id": str(row[2]), "chunk_id": str(row[3]),
                "excerpt": str(row[4])[:1400], "chunk_index": int(row[5]),
                "start_offset": int(row[6]), "end_offset": int(row[7]),
                "match_score": 0.0, "status": str(row[8]),
            }
            for row in rows
            if row[0] and row[3] and str(row[2]) == department_id
            and str(row[8]).upper() == "APPROVED"
        ]

    @staticmethod
    def search_approved(query: str, department_id: str, *, limit: int = 5) -> list[dict[str, Any]]:
        """Lexical recall only, with status and department scoped in Snowflake SQL."""
        tokens = list(dict.fromkeys(re.findall(r"[^\W_]{2,}", query.casefold(), flags=re.UNICODE)))[:6]
        if not tokens:
            return []
        clauses = " OR ".join(["c.content ILIKE %s"] * len(tokens))
        sql = f"""
            SELECT d.id, d.title, d.department_id, c.id, c.content, c.ordinal_index,
                   c.start_offset, c.end_offset, d.status
            FROM KNOWLEDGE_STUDIO.reference_chunks c
            JOIN KNOWLEDGE_STUDIO.reference_documents d ON c.document_id = d.id
            WHERE d.department_id = %s AND c.department_id = %s
              AND d.status = 'APPROVED' AND ({clauses})
            ORDER BY d.title, c.ordinal_index
            LIMIT 150
        """
        # Escaped SQL LIKE wildcards: tokens contain Unicode letters/numbers only.
        search_params = tuple(f"%{token}%" for token in tokens)
        with get_snowflake_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (department_id, department_id, *search_params))
                rows = cur.fetchall()
        scored = []
        for row in rows:
            if str(row[2]) != department_id or str(row[8]).upper() != "APPROVED":
                continue  # defence-in-depth against bad cache/mocked-provider boundaries
            content = str(row[4])
            score = sum(1 for token in tokens if token in content.casefold()) / len(tokens)
            scored.append({
                "document_id": str(row[0]), "document_title": str(row[1]),
                "department_id": str(row[2]), "chunk_id": str(row[3]),
                "excerpt": content[:1400], "chunk_index": int(row[5]),
                "start_offset": int(row[6]), "end_offset": int(row[7]),
                "match_score": round(score, 3),
                "status": str(row[8]),
            })
        return sorted(scored, key=lambda row: (-row["match_score"], row["document_title"], row["chunk_index"]))[:limit]
