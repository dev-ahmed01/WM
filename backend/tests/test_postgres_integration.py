"""Real PostgreSQL integration (dedicated CI service; no Snowflake credentials)."""
from __future__ import annotations

import os
import uuid

import psycopg
import pytest

from app.core.database import close_postgres_pool, get_postgres_connection, ping
from app.repositories.user_repository import UserRepository
from app.repositories.reference_document_repository import ReferenceDocumentRepository
from app.services.ingestion import IngestionService
from app.core.security import hash_password


@pytest.mark.live_integration
def test_postgres_schema_auth_source_storage_and_reference_approval():
    dsn = os.environ["DATABASE_URL"]
    dept = "test_" + uuid.uuid4().hex[:10]
    user = "user_" + uuid.uuid4().hex[:10]
    doc_id = uuid.uuid4().hex
    role = "role_" + uuid.uuid4().hex[:10]
    source_uri = None
    with psycopg.connect(dsn, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO security.departments (id,code,name) VALUES (%s,%s,%s)",
                (dept, dept.upper(), "Postgres integration"),
            )
            cur.execute(
                "INSERT INTO security.roles (id,name,permission_set) VALUES (%s,%s,%s::jsonb)",
                (role, "admin", "{}"),
            )
            cur.execute(
                "INSERT INTO security.users (id,email,hashed_password,department_id) VALUES (%s,%s,%s,%s)",
                (user, f"{user}@example.test", hash_password("development-test-only"), dept),
            )
            cur.execute(
                "INSERT INTO security.user_roles (user_id,role_id) VALUES (%s,%s)", (user, role)
            )
    try:
        assert ping()
        profile = UserRepository.get_user_by_email(f"{user}@example.test")
        assert profile is not None
        assert profile["department_id"] == dept and profile["role"] == "admin"
        data = b"Damaged cartons must be isolated and reported to the supervisor."
        source_uri = IngestionService.stage_reference_file(data, "receiving.txt", dept, doc_id)
        assert source_uri.startswith("pgobj:")
        with get_postgres_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT department_id, content FROM shared.source_objects WHERE id = %s",
                    (source_uri.split(":")[1],),
                )
                owner, stored = cur.fetchone()
                assert owner == dept and bytes(stored) == data
        registered = ReferenceDocumentRepository.save_draft(
            document_id=doc_id,
            department_id=dept,
            title="Damaged goods",
            filename="receiving.txt",
            file_type="txt",
            mime_type="text/plain",
            stage_uri=source_uri,
            raw=data,
            extracted_text=data.decode(),
            warnings=[],
            created_by=user,
        )
        assert registered["status"] == "DRAFT"
        assert not ReferenceDocumentRepository.search_approved("damaged carton", dept)
        assert ReferenceDocumentRepository.change_status(doc_id, dept, user, action="approve")
        found = ReferenceDocumentRepository.search_approved("damaged carton", dept)
        assert found and found[0]["document_id"] == doc_id
        assert not ReferenceDocumentRepository.search_approved("damaged carton", "other_department")
        assert ReferenceDocumentRepository.change_status(doc_id, dept, user, action="archive")
        assert not ReferenceDocumentRepository.search_approved("damaged carton", dept)
        assert IngestionService.remove_staged_files([source_uri]) == 1
        source_uri = None
    finally:
        close_postgres_pool()
        with psycopg.connect(dsn, autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM knowledge_studio.reference_chunks WHERE document_id = %s", (doc_id,))
                cur.execute("DELETE FROM knowledge_studio.reference_documents WHERE id = %s", (doc_id,))
                if source_uri:
                    cur.execute("DELETE FROM shared.source_objects WHERE id = %s", (source_uri.split(":")[1],))
                cur.execute("DELETE FROM security.user_roles WHERE user_id = %s", (user,))
                cur.execute("DELETE FROM security.users WHERE id = %s", (user,))
                cur.execute("DELETE FROM security.roles WHERE id = %s", (role,))
                cur.execute("DELETE FROM security.departments WHERE id = %s", (dept,))
