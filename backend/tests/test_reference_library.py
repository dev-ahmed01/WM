"""Reference knowledge separation, permissions and transactional regression tests."""
from contextlib import contextmanager
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.reference_knowledge import router
from app.core.security import create_access_token
from app.repositories.reference_document_repository import (
    ReferenceDocumentRepository, chunk_reference_text,
)
from app.services.document_extraction import extract_document, DocumentExtractionError
from app.services.ingestion import IngestionService

app = FastAPI()
app.include_router(router, prefix="/api/v1")
client = TestClient(app)
ADMIN = create_access_token("admin_01", "admin", "receiving")
EMPLOYEE = create_access_token("employee_01", "employee", "receiving")


def auth(token):
    return {"Authorization": f"Bearer {token}"}


class Cursor:
    def __init__(self, rows=None, rowcount=1, fail_insert=False):
        self.rows = rows or []
        self.rowcount = rowcount
        self.statements = []
        self.fail_insert = fail_insert

    def execute(self, sql, params=None):
        self.statements.append((sql, params))
        if self.fail_insert and "INSERT INTO" in sql:
            raise RuntimeError("Simulated DB outage")
        return self

    def executemany(self, sql, rows):
        self.statements.append((sql, rows))

    def fetchall(self):
        return self.rows

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class Connection:
    def __init__(self, cursor):
        self.value = cursor

    def cursor(self):
        return self.value


def patch_db(monkeypatch, cursor):
    @contextmanager
    def connection():
        yield Connection(cursor)
    monkeypatch.setattr(
        "app.repositories.reference_document_repository.get_snowflake_connection",
        connection,
    )


def test_chunk_offsets_reconstruct_exact_source():
    source = ("Seal number checked; damaged boxes quarantined.\n" * 95)
    chunks = chunk_reference_text(source, "f" * 32, size=230, overlap=30)
    assert len(chunks) > 5
    assert all(source[item.start_offset:item.end_offset] == item.content for item in chunks)
    assert chunks[0].start_offset == 0
    assert chunks[-1].end_offset == len(source)
    assert all(a.end_offset >= b.start_offset for a, b in zip(chunks, chunks[1:]))


def test_import_is_not_an_executable_workflow():
    extracted = extract_document("policy.txt", b"Never infer that a parcel is safe.")
    assert extracted.content.startswith("Never")
    assert not hasattr(extracted, "workflow_state")


def test_malformed_reference_rejected_before_any_stage_call():
    response = client.post(
        "/api/v1/knowledge/references",
        headers=auth(ADMIN),
        files={"file": ("danger.exe", b"malicious", "application/octet-stream")},
        data={"department_id": "receiving", "title": "Unsafe"},
    )
    assert response.status_code == 422
    assert response.json()["detail"]["error_code"] == "DOCUMENT_EXTRACTION_FAILED"


def test_employee_cannot_upload_or_approve():
    upload = client.post(
        "/api/v1/knowledge/references",
        headers=auth(EMPLOYEE),
        files={"file": ("valid.txt", b"some source", "text/plain")},
        data={"department_id": "receiving", "title": "Policy"},
    )
    approval = client.post(
        "/api/v1/knowledge/references/doc1/approve?department_id=receiving",
        headers=auth(EMPLOYEE),
    )
    assert upload.status_code == 403
    assert approval.status_code == 403


def test_authentication_required():
    response = client.get("/api/v1/knowledge/references/search?q=damage")
    assert response.status_code == 401


def test_search_department_comes_from_identity_not_query(monkeypatch):
    captured = {}
    async def search(q, department, *, limit):
        captured.update(query=q, department=department, limit=limit)
        return []
    monkeypatch.setattr("app.api.v1.reference_knowledge.ReferenceRetrievalService.search", search)
    response = client.get(
        "/api/v1/knowledge/references/search?q=damaged&department_id=secret",
        headers=auth(EMPLOYEE),
    )
    assert response.status_code == 200
    assert captured["department"] == "receiving"
    assert response.json()["department_id"] == "receiving"


def test_sql_filters_approved_and_both_department_columns(monkeypatch):
    cursor = Cursor(rows=[
        ("doc1", "Receipts", "receiving", "chunk1", "Damaged parcel", 0, 0, 14, "APPROVED"),
        ("doc2", "Other", "other", "chunk2", "Damaged parcel", 0, 0, 14, "APPROVED"),
    ])
    patch_db(monkeypatch, cursor)
    result = ReferenceDocumentRepository.search_approved("damaged", "receiving")
    assert len(result) == 1
    assert result[0]["document_id"] == "doc1"
    sql, params = cursor.statements[0]
    assert "d.status = 'APPROVED'" in sql
    assert "d.department_id = %s AND c.department_id = %s" in sql
    assert params[:2] == ("receiving", "receiving")
    assert "damaged" not in sql


def test_save_is_one_transaction_and_starts_unapproved(monkeypatch):
    cursor = Cursor()
    patch_db(monkeypatch, cursor)
    result = ReferenceDocumentRepository.save_draft(
        document_id="a" * 32, department_id="receiving", title="Policy",
        filename="policy.txt", file_type="txt", mime_type="text/plain",
        stage_uri="@RAW_OWD_STAGE/reference/receiving/doc/policy.txt",
        raw=b"check all labels", extracted_text="check all labels",
        warnings=[], created_by="admin_01",
    )
    assert result["status"] == "DRAFT"
    assert cursor.statements[0][0] == "BEGIN"
    assert "INSERT INTO KNOWLEDGE_STUDIO.reference_documents" in cursor.statements[1][0]
    assert "INSERT INTO KNOWLEDGE_STUDIO.reference_chunks" in cursor.statements[2][0]
    assert cursor.statements[-1][0] == "COMMIT"


def test_save_rolls_back_when_metadata_write_fails(monkeypatch):
    cursor = Cursor(fail_insert=True)
    patch_db(monkeypatch, cursor)
    with pytest.raises(RuntimeError):
        ReferenceDocumentRepository.save_draft(
            document_id="a" * 32, department_id="receiving", title="Policy",
            filename="policy.txt", file_type="txt", mime_type="text/plain",
            stage_uri="@RAW_OWD_STAGE/reference/receiving/doc/policy.txt",
            raw=b"test document", extracted_text="test document",
            warnings=[], created_by="admin_01",
        )
    assert cursor.statements[-1][0] == "ROLLBACK"
    assert not any(sql == "COMMIT" for sql, _ in cursor.statements)


def test_review_requires_correct_status_and_scoped_id(monkeypatch):
    cursor = Cursor(rowcount=0)
    patch_db(monkeypatch, cursor)
    assert not ReferenceDocumentRepository.change_status(
        "doc1", "receiving", "admin_01", action="approve",
    )
    sql, params = cursor.statements[0]
    assert "status = %s" in sql and "department_id = %s" in sql
    assert params == ("APPROVED", "admin_01", "doc1", "receiving", "DRAFT")
    assert cursor.statements[-1][0] == "COMMIT"


def test_stage_rejects_invalid_department_before_put():
    with pytest.raises(Exception, match="department"):
        IngestionService.stage_reference_file(
            b"hello", "policy.txt", "../../hijack", "a" * 32,
        )


def test_extract_caps_document_text():
    with pytest.raises(DocumentExtractionError, match="1,000,000"):
        extract_document("large.txt", b"z" * 1_000_001)
