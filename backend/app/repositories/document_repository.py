"""Enterprise Document Repository.

Provides data access interfaces for querying canonical Enterprise Knowledge Document entities,
preserved raw markdown, local analysis metadata, first-class chunks, and lineage audit trails.
"""

import logging
from typing import Optional, Dict, Any, List
from app.core.database import get_snowflake_connection

logger = logging.getLogger("repositories.document")


class DocumentRepository:
    """Repository interface for KNOWLEDGE_STUDIO enterprise document tables."""

    @staticmethod
    def get_document_by_id(document_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves a document entity record by document_id."""
        if get_snowflake_connection is None:
            return None
        try:
            with get_snowflake_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT id, workflow_id, workflow_version_id, document_name, original_filename,
                               stage_uri, relative_path, directory, extension, mime_type, uploaded_at,
                               file_size_bytes, md5_hash, sha256_hash, compiler_version, parser_version,
                               source_type, language_code, author, reviewer, approval_status, description
                        FROM KNOWLEDGE_STUDIO.knowledge_documents
                        WHERE id = %s
                        """,
                        (document_id,),
                    )
                    row = cur.fetchone()
                    if row:
                        cols = [c[0].lower() for c in cur.description]
                        return dict(zip(cols, row))
        except Exception as exc:
            logger.warning(f"Error fetching document by id '{document_id}': {exc}")
        return None

    @staticmethod
    def get_document_by_version_id(workflow_version_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves a document entity record by workflow_version_id."""
        if get_snowflake_connection is None:
            return None
        try:
            with get_snowflake_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT id, workflow_id, workflow_version_id, document_name, original_filename,
                               stage_uri, relative_path, directory, extension, mime_type, uploaded_at,
                               file_size_bytes, md5_hash, sha256_hash, compiler_version, parser_version,
                               source_type, language_code, author, reviewer, approval_status, description
                        FROM KNOWLEDGE_STUDIO.knowledge_documents
                        WHERE workflow_version_id = %s
                        """,
                        (workflow_version_id,),
                    )
                    row = cur.fetchone()
                    if row:
                        cols = [c[0].lower() for c in cur.description]
                        return dict(zip(cols, row))
        except Exception as exc:
            logger.warning(f"Error fetching document by version_id '{workflow_version_id}': {exc}")
        return None

    @staticmethod
    def get_document_content(document_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves preserved raw markdown, frontmatter, and structural elements."""
        if get_snowflake_connection is None:
            return None
        try:
            with get_snowflake_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT id, document_id, workflow_version_id, raw_markdown, normalized_markdown,
                               frontmatter_yaml, body_markdown
                        FROM KNOWLEDGE_STUDIO.knowledge_document_contents
                        WHERE document_id = %s
                        """,
                        (document_id,),
                    )
                    row = cur.fetchone()
                    if row:
                        cols = [c[0].lower() for c in cur.description]
                        return dict(zip(cols, row))
        except Exception as exc:
            logger.warning(f"Error fetching document content for '{document_id}': {exc}")
        return None

    @staticmethod
    def get_document_chunks(document_id: str) -> List[Dict[str, Any]]:
        """Retrieves first-class vector chunk objects associated with a document."""
        if get_snowflake_connection is None:
            return []
        try:
            with get_snowflake_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT id, document_id, workflow_version_id, state_id, step_id,
                               chunk_order, character_count, token_count, chunk_content,
                               embedding_ref, vector_status, chunk_hash, chunk_type, section_name
                        FROM KNOWLEDGE_STUDIO.knowledge_document_chunks
                        WHERE document_id = %s
                        ORDER BY chunk_order ASC
                        """,
                        (document_id,),
                    )
                    rows = cur.fetchall()
                    cols = [c[0].lower() for c in cur.description]
                    return [dict(zip(cols, r)) for r in rows]
        except Exception as exc:
            logger.warning(f"Error fetching document chunks for '{document_id}': {exc}")
            return []

    @staticmethod
    def get_document_lineage(document_id: str) -> List[Dict[str, Any]]:
        """Retrieves audit lineage records for a document."""
        if get_snowflake_connection is None:
            return []
        try:
            with get_snowflake_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT id, document_id, workflow_version_id, stage_file_uri, source_markdown_hash,
                               parser_name, ast_hash, compiler_name, loader_name, status, executed_by, execution_notes, created_at
                        FROM KNOWLEDGE_STUDIO.knowledge_document_lineage
                        WHERE document_id = %s
                        ORDER BY created_at ASC
                        """,
                        (document_id,),
                    )
                    rows = cur.fetchall()
                    cols = [c[0].lower() for c in cur.description]
                    return [dict(zip(cols, r)) for r in rows]
        except Exception as exc:
            logger.warning(f"Error fetching document lineage for '{document_id}': {exc}")
            return []
