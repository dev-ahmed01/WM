"""Real PostgreSQL acceptance for department-scoped SOP draft provenance/review."""
from types import SimpleNamespace
from uuid import uuid4
import psycopg
import pytest
from app.core.config import settings
from app.repositories.procedure_draft_repository import (
    ProcedureDraftRepository,DraftConflict,DraftNotFound,
)

@pytest.mark.live_integration
def test_private_source_backed_procedure_draft_revision_and_review():
    suffix=uuid4().hex[:8]
    department="pd_a_"+suffix
    foreign="pd_b_"+suffix
    admin="pd_admin_"+suffix
    raw=b"Inbound receiving:\n1. Inspect the original cargo seal on arrival.\n2. Record the condition of the outer cartons.\n"
    doc=SimpleNamespace(filename="receiving.txt",file_type="txt",
                        content=raw.decode(),warnings=[])
    draft_id=None
    src_id=None
    with psycopg.connect(settings.DATABASE_URL,autocommit=True) as conn:
        with conn.cursor() as cur:
            for dept in (department,foreign):
                cur.execute("INSERT INTO security.departments(id,code,name) VALUES(%s,%s,%s)",
                            (dept,dept.upper(),dept))
            cur.execute("""INSERT INTO security.users(id,email,hashed_password,department_id)
                VALUES(%s,%s,'synthetic',%s)""",(admin,admin+"@example.test",department))
    try:
        draft=ProcedureDraftRepository.create(department,admin,doc,raw,"Inbound inspection")
        draft_id=draft["id"]
        assert draft["status"]=="draft" and draft["revision"]==1
        assert len(draft["steps"])==2
        assert all(step["reviewed"] is False for step in draft["steps"])
        assert draft["source_sha256"]
        assert b"record" in raw.lower()
        with pytest.raises(DraftNotFound):
            ProcedureDraftRepository.get(foreign,draft_id)
        assert len(ProcedureDraftRepository.list(department))==1
        assert ProcedureDraftRepository.list(foreign)==[]
        with pytest.raises(DraftConflict):
            ProcedureDraftRepository.review(department,admin,draft_id,1)
        revised=[{**step,"reviewed":True} for step in draft["steps"]]
        updated=ProcedureDraftRepository.update(
            department,admin,draft_id,1,"Inbound receiving procedure",revised
        )
        assert updated["revision"]==2 and updated["status"]=="draft"
        with pytest.raises(DraftConflict):
            ProcedureDraftRepository.update(
                department,admin,draft_id,1,"Stale edit rejected",revised
            )
        review=ProcedureDraftRepository.review(department,admin,draft_id,2)
        assert review["status"]=="reviewed" and review["revision"]==3
        with pytest.raises(DraftConflict):
            ProcedureDraftRepository.review(department,admin,draft_id,2)
        edited=ProcedureDraftRepository.update(
            department,admin,draft_id,3,"Inbound receiving edited",revised
        )
        assert edited["status"]=="draft" and edited["reviewed_by"] is None
        assert edited["revision"]==4
        with psycopg.connect(settings.DATABASE_URL) as conn:
            with conn.cursor() as cur:
                cur.execute("""SELECT source_object_id FROM knowledge_studio.procedure_drafts
                    WHERE id=%s""",(draft_id,))
                src_id=cur.fetchone()[0]
                cur.execute("SELECT content FROM shared.source_objects WHERE id=%s",(src_id,))
                assert bytes(cur.fetchone()[0])==raw
                cur.execute("""SELECT action,revision FROM knowledge_studio.procedure_draft_events
                    WHERE draft_id=%s ORDER BY seq""",(draft_id,))
                assert cur.fetchall()==[
                    ("imported",1),("edited",2),("reviewed",3),("edited",4)]
                cur.execute("BEGIN")
                cur.execute("SET LOCAL ROLE workmate_scoped_reader")
                cur.execute("""SELECT count(*) FROM knowledge_studio.procedure_drafts
                    WHERE id=%s""",(draft_id,))
                assert cur.fetchone()==(0,)
                cur.execute("SELECT set_config('workmate.department_id',%s,true)",(foreign,))
                cur.execute("SELECT count(*) FROM knowledge_studio.procedure_drafts WHERE id=%s",(draft_id,))
                assert cur.fetchone()==(0,)
                cur.execute("SELECT set_config('workmate.department_id',%s,true)",(department,))
                cur.execute("SELECT count(*) FROM knowledge_studio.procedure_drafts WHERE id=%s",(draft_id,))
                assert cur.fetchone()==(1,)
                cur.execute("ROLLBACK")
    finally:
        with psycopg.connect(settings.DATABASE_URL,autocommit=True) as conn:
            with conn.cursor() as cur:
                if draft_id:
                    cur.execute("DELETE FROM knowledge_studio.procedure_draft_events WHERE draft_id=%s",(draft_id,))
                    cur.execute("DELETE FROM knowledge_studio.procedure_drafts WHERE id=%s",(draft_id,))
                if src_id:
                    cur.execute("DELETE FROM shared.source_objects WHERE id=%s",(src_id,))
                cur.execute("DELETE FROM security.users WHERE id=%s",(admin,))
                cur.execute("DELETE FROM security.departments WHERE id=ANY(%s)",([department,foreign],))
