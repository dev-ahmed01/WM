"""Database contract: real queue, assignee isolation and tenant-level row security."""
from uuid import uuid4
import psycopg
import pytest
from app.core.config import settings
from app.repositories.work_item_repository import WorkItemRepository


@pytest.mark.live_integration
def test_task_creation_visibility_and_department_rls():
    suffix=uuid4().hex[:8]
    d1,d2="wi_a_"+suffix,"wi_b_"+suffix
    creator,employee,outsider="mgr_"+suffix,"emp_"+suffix,"other_"+suffix
    identifier=None
    with psycopg.connect(settings.DATABASE_URL,autocommit=True) as conn:
        with conn.cursor() as cur:
            for department in (d1,d2):
                cur.execute("INSERT INTO security.departments(id,code,name) VALUES(%s,%s,%s)",
                            (department,department.upper(),department))
            for actor,department in ((creator,d1),(employee,d1),(outsider,d2)):
                cur.execute("""INSERT INTO security.users(id,email,hashed_password,department_id)
                               VALUES(%s,%s,'synthetic',%s)""",
                            (actor,actor+"@example.test",department))
    try:
        assert WorkItemRepository.create(d1,creator,"Unsafe wrong team task",
               "receiving","high","","",outsider) is None
        task=WorkItemRepository.create(d1,creator,"Inspect inbound dock safety",
                  "receiving","high","Use current approved SOP.","INB-101",employee)
        assert task and task["status"] == "queued"
        identifier=task["id"]
        assert task["assigned_to"]==employee
        assert len(WorkItemRepository.list(d1,employee,False))==1
        assert WorkItemRepository.list(d1,creator,False)==[]
        assert len(WorkItemRepository.list(d1,creator,True))==1
        assert WorkItemRepository.list(d2,outsider,True)==[]
        assert WorkItemRepository.get(d1,creator,False,identifier) is None
        assert WorkItemRepository.get(d2,outsider,True,identifier) is None
        assert WorkItemRepository.get(d1,employee,False,identifier)["id"]==identifier
        with psycopg.connect(settings.DATABASE_URL) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT action FROM workmate_copilot.work_item_events WHERE work_item_id=%s",(identifier,))
                assert cur.fetchall()==[("created",)]
                cur.execute("BEGIN")
                cur.execute("SET LOCAL ROLE workmate_scoped_reader")
                cur.execute("SELECT count(*) FROM workmate_copilot.work_items WHERE id=%s",(identifier,))
                assert cur.fetchone()==(0,)
                cur.execute("SELECT set_config('workmate.department_id',%s,true)",(d2,))
                cur.execute("SELECT count(*) FROM workmate_copilot.work_items WHERE id=%s",(identifier,))
                assert cur.fetchone()==(0,)
                cur.execute("SELECT set_config('workmate.department_id',%s,true)",(d1,))
                cur.execute("SELECT count(*) FROM workmate_copilot.work_items WHERE id=%s",(identifier,))
                assert cur.fetchone()==(1,)
                cur.execute("ROLLBACK")
    finally:
        with psycopg.connect(settings.DATABASE_URL,autocommit=True) as conn:
            with conn.cursor() as cur:
                if identifier:
                    cur.execute("DELETE FROM workmate_copilot.work_item_events WHERE work_item_id=%s",(identifier,))
                    cur.execute("DELETE FROM workmate_copilot.work_items WHERE id=%s",(identifier,))
                cur.execute("DELETE FROM security.users WHERE id=ANY(%s)",([creator,employee,outsider],))
                cur.execute("DELETE FROM security.departments WHERE id=ANY(%s)",([d1,d2],))
