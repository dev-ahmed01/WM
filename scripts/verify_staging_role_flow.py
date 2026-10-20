"""Verify real non-owner PostgreSQL login can complete governed reference lifecycle.

Disposable CI only. Tests tenant RLS, scoped upload, approval and archive.
Never points at a hosted DB without WORKMATE_STAGING_ROLE_SMOKE=1.
"""
from __future__ import annotations
import os
from uuid import uuid4

import psycopg

from app.core.config import settings
from app.core.database import close_postgres_pool
from app.core.security import hash_password
from app.repositories.reference_document_repository import ReferenceDocumentRepository
from app.services.ingestion import IngestionService
from app.repositories.pilot_repository import PilotFeedbackRepository


def verify() -> None:
    if os.getenv("WORKMATE_STAGING_ROLE_SMOKE") != "1" or os.getenv("APP_ENV") != "dev":
        raise RuntimeError("This smoke uses disposable dev CI databases only")
    admin_dsn = os.environ["MIGRATION_DATABASE_URL"]
    runtime_dsn = os.environ["DATABASE_URL"]
    suffix = uuid4().hex[:10]
    dept_a,dept_b = f"staga_{suffix}",f"stagb_{suffix}"
    user_id,doc_id = f"admin_{suffix}",uuid4().hex
    source_id = None
    with psycopg.connect(admin_dsn,autocommit=True) as conn:
        with conn.cursor() as cur:
            for dept in (dept_a,dept_b):
                cur.execute("INSERT INTO security.departments (id,code,name) VALUES (%s,%s,%s)",
                            (dept,dept.upper(),"Stage role acceptance"))
            cur.execute("""INSERT INTO security.users (id,email,hashed_password,department_id)
                           VALUES (%s,%s,%s,%s)""",
                        (user_id,f"{user_id}@example.test",hash_password("ci-only-password"),dept_a))
    try:
        settings.POSTGRES_RLS_REFERENCES = True
        original = b"Inspect the carton security seal and quarantine damaged boxes."
        stage = IngestionService.stage_reference_file(original,"security-seal.txt",dept_a,doc_id)
        source_id = stage.split(":")[1]
        draft = ReferenceDocumentRepository.save_draft(
            document_id=doc_id, department_id=dept_a,title="Staging receiving",
            filename="security-seal.txt",file_type="txt",mime_type="text/plain",
            stage_uri=stage,raw=original,extracted_text=original.decode(),
            warnings=[],created_by=user_id,
        )
        assert draft["status"]=="DRAFT"
        assert [row["id"] for row in ReferenceDocumentRepository.list_documents(dept_a) if row["id"]==doc_id]==[doc_id]
        assert ReferenceDocumentRepository.get_document(doc_id,dept_b) is None
        assert not ReferenceDocumentRepository.search_approved("security seal",dept_a)
        assert ReferenceDocumentRepository.change_status(doc_id,dept_a,user_id,action="approve")
        assert any(r["document_id"]==doc_id for r in ReferenceDocumentRepository.search_approved("security seal",dept_a))
        assert not ReferenceDocumentRepository.search_approved("security seal",dept_b)
        # The non-owner PostgreSQL runtime can submit and summarize within
        # the chosen department but never read pilot feedback from another one.
        pilot_id = PilotFeedbackRepository.save(dept_a, user_id, "reference", "helpful", "none", 5)
        assert pilot_id is not None
        assert PilotFeedbackRepository.summary(dept_a)["total"] == 1
        assert PilotFeedbackRepository.summary(dept_b)["total"] == 0
        with psycopg.connect(runtime_dsn) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT count(*) FROM knowledge_studio.reference_documents WHERE id=%s",(doc_id,))
                assert cur.fetchone()==(0,), "Unscoped runtime SQL saw protected document"
                cur.execute("SELECT count(*) FROM shared.source_objects WHERE id=%s",(source_id,))
                assert cur.fetchone()==(0,), "Unscoped runtime SQL saw source bytes"
                cur.execute("SELECT count(*) FROM shared.pilot_feedback WHERE id=%s",(pilot_id,))
                assert cur.fetchone()==(0,), "Unscoped runtime SQL saw pilot feedback"
                cur.execute("BEGIN")
                cur.execute("SET LOCAL ROLE workmate_scoped_reader")
                cur.execute("SELECT set_config('workmate.department_id',%s,true)",(dept_b,))
                cur.execute("SELECT count(*) FROM knowledge_studio.reference_documents WHERE id=%s",(doc_id,))
                assert cur.fetchone()==(0,), "Cross-tenant SQL access"
                cur.execute("SELECT count(*) FROM shared.pilot_feedback WHERE id=%s",(pilot_id,))
                assert cur.fetchone()==(0,), "Cross-tenant pilot feedback SQL access"
                cur.execute("ROLLBACK")
        assert ReferenceDocumentRepository.change_status(doc_id,dept_a,user_id,action="archive")
        assert not ReferenceDocumentRepository.search_approved("security seal",dept_a)
        assert IngestionService.remove_staged_files([stage],department_id=dept_a)==1
        source_id=None
        print("STAGING RUNTIME ROLE: scoped create/approve/archive, tenant boundaries, RLS read denial PASS")
    finally:
        settings.POSTGRES_RLS_REFERENCES = False
        close_postgres_pool()
        with psycopg.connect(admin_dsn,autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM shared.pilot_feedback WHERE reporter_user_id=%s",(user_id,))
                cur.execute("DELETE FROM knowledge_studio.reference_chunks WHERE document_id=%s",(doc_id,))
                cur.execute("DELETE FROM knowledge_studio.reference_documents WHERE id=%s",(doc_id,))
                if source_id:
                    cur.execute("DELETE FROM shared.source_objects WHERE id=%s",(source_id,))
                cur.execute("DELETE FROM security.users WHERE id=%s",(user_id,))
                cur.execute("DELETE FROM security.departments WHERE id=ANY(%s)",([dept_a,dept_b],))


if __name__=="__main__":
    verify()
