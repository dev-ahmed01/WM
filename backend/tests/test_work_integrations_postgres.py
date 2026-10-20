"""Phase 6A real PostgreSQL: idempotency, separate human review and RLS."""
from uuid import uuid4

import psycopg
import pytest

from app.core.config import settings
from app.repositories.work_integration_intake_repository import (
    IntegrationIntakeRepository,IntegrationConflict,IntegrationNotFound,
)
from app.repositories.work_item_repository import WorkItemRepository


@pytest.mark.live_integration
def test_real_wms_intake_is_deduplicated_and_only_queues_after_independent_approval():
    k=uuid4().hex[:9]
    dept,foreign="int_a_"+k,"int_b_"+k
    sender,reviewer,worker,outsider=[
        p+k for p in ("int_sender_","int_reviewer_","int_worker_","int_out_")
    ]
    manager_role,worker_role="int_role_m_"+k,"int_role_e_"+k
    entry=None
    new_work=None
    with psycopg.connect(settings.DATABASE_URL,autocommit=True) as conn:
        with conn.cursor() as cur:
            for d in (dept,foreign):
                cur.execute("INSERT INTO security.departments(id,code,name) VALUES(%s,%s,%s)",(d,d.upper(),d))
            for role,name in ((manager_role,"manager"),(worker_role,"employee")):
                cur.execute("""INSERT INTO security.roles(id,name,permission_set)
                    VALUES(%s,%s,'{}'::jsonb)""",(role,name))
            for user,d in ((sender,dept),(reviewer,dept),(worker,dept),(outsider,foreign)):
                cur.execute("""INSERT INTO security.users(id,email,hashed_password,department_id,status)
                    VALUES (%s,%s,'synthetic',%s,'active')""",(user,user+"@example.test",d))
            for actor,role in ((sender,manager_role),(reviewer,manager_role),(worker,worker_role),
                               (outsider,manager_role)):
                cur.execute("INSERT INTO security.user_roles(user_id,role_id) VALUES (%s,%s)",(actor,role))
    try:
        data={
            "source_system":"custom_wms",
            "external_event_id":"receipt.received."+k,
            "external_work_id":"RECEIPT-"+k,
            "title":"Review cartons in inbound dock",
            "work_type":"receiving",
            "priority":"high",
            "instructions":"Compare the sealed receipt with the expected lot.",
            "assigned_to":worker,
        }
        staged=IntegrationIntakeRepository.stage(dept,sender,data)
        entry=staged["id"]
        assert staged["status"]=="pending" and staged["replayed"] is False
        assert WorkItemRepository.list(dept,reviewer,True)==[]
        retry=IntegrationIntakeRepository.stage(dept,sender,dict(reversed(list(data.items()))))
        assert retry["id"]==entry and retry["replayed"] is True
        altered={**data,"priority":"standard"}
        with pytest.raises(IntegrationConflict):
            IntegrationIntakeRepository.stage(dept,sender,altered)
        with pytest.raises(IntegrationConflict):
            IntegrationIntakeRepository.stage(dept,sender,{
                **data,"external_event_id":"receipt.changed."+k,
            })
        with pytest.raises(IntegrationConflict):
            IntegrationIntakeRepository.stage(dept,sender,{
                **data,"external_work_id":"other-"+k,
            })
        with pytest.raises(IntegrationConflict):
            IntegrationIntakeRepository.decide(dept,sender,entry,"accepted",
                "Submitter is not allowed to accept their own import.")
        with pytest.raises(IntegrationNotFound):
            IntegrationIntakeRepository.decide(foreign,outsider,entry,"accepted",
                "Foreign department must not accept an import.")
        with pytest.raises(IntegrationConflict):
            IntegrationIntakeRepository.decide(dept,reviewer,entry,"approved",
                "Unsupported review decision cannot make a task.")
        accepted=IntegrationIntakeRepository.decide(dept,reviewer,entry,"accepted",
            "Shipment has been reconciled to incoming invoice for a separate SOP assignment.")
        new_work=accepted["work_item_id"]
        assert accepted["status"]=="accepted" and new_work.startswith("wrk_")
        assert accepted["decided_by"]==reviewer
        imported=WorkItemRepository.get(dept,reviewer,True,new_work)
        assert imported["status"]=="queued" and imported["workflow_version_id"] is None
        assert imported["execution_session_id"] is None
        assert imported["external_reference"]=="CUSTOM_WMS:"+data["external_work_id"]
        assert WorkItemRepository.get(foreign,outsider,True,new_work) is None
        with pytest.raises(IntegrationConflict):
            IntegrationIntakeRepository.decide(dept,reviewer,entry,"accepted",
                "Duplicate acceptance cannot create a second task.")
        retry_after=IntegrationIntakeRepository.stage(dept,sender,data)
        assert retry_after["id"]==entry and retry_after["work_item_id"]==new_work
        assert retry_after["replayed"] is True
        with psycopg.connect(settings.DATABASE_URL) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT action,event_payload FROM workmate_copilot.work_item_events WHERE work_item_id=%s",(new_work,))
                events=cur.fetchall()
                assert len(events)==1 and events[0][0]=="integration_imported"
                assert events[0][1]["intake_id"]==entry
                cur.execute("SELECT COUNT(*) FROM workmate_copilot.work_items WHERE external_reference=%s",
                            ("CUSTOM_WMS:"+data["external_work_id"],))
                assert cur.fetchone()[0]==1
                cur.execute("BEGIN")
                cur.execute("SET LOCAL ROLE workmate_scoped_reader")
                cur.execute("SELECT COUNT(*) FROM workmate_copilot.work_integration_intake WHERE id=%s",(entry,))
                assert cur.fetchone()[0]==0
                cur.execute("SELECT set_config('workmate.department_id',%s,true)",(foreign,))
                cur.execute("SELECT COUNT(*) FROM workmate_copilot.work_integration_intake WHERE id=%s",(entry,))
                assert cur.fetchone()[0]==0
                cur.execute("SELECT set_config('workmate.department_id',%s,true)",(dept,))
                cur.execute("SELECT COUNT(*) FROM workmate_copilot.work_integration_intake WHERE id=%s",(entry,))
                assert cur.fetchone()[0]==1
                cur.execute("ROLLBACK")
    finally:
        with psycopg.connect(settings.DATABASE_URL,autocommit=True) as conn:
            with conn.cursor() as cur:
                if entry:
                    cur.execute("DELETE FROM workmate_copilot.work_integration_intake WHERE id=%s",(entry,))
                if new_work:
                    cur.execute("DELETE FROM workmate_copilot.work_item_events WHERE work_item_id=%s",(new_work,))
                    cur.execute("DELETE FROM workmate_copilot.work_items WHERE id=%s",(new_work,))
                cur.execute("DELETE FROM security.user_roles WHERE role_id IN (%s,%s)",(manager_role,worker_role))
                cur.execute("DELETE FROM security.users WHERE id=ANY(%s)",([sender,reviewer,worker,outsider],))
                cur.execute("DELETE FROM security.roles WHERE id IN (%s,%s)",(manager_role,worker_role))
                cur.execute("DELETE FROM security.departments WHERE id=ANY(%s)",([dept,foreign],))
