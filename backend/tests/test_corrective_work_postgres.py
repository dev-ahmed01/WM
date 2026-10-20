"""Phase 4C acceptance: two-person corrective task authorization on disposable Postgres."""
from uuid import uuid4
import psycopg
import pytest
from app.core.config import settings
from app.repositories.work_exception_repository import (
    WorkExceptionRepository,open_case,CaseConflict,CaseNotFound,
)
from app.repositories.work_corrective_repository import CorrectiveWorkRepository
from app.repositories.work_execution_repository import WorkExecutionRepository


@pytest.mark.live_integration
def test_independent_corrective_authorization_preserves_original_hold_and_rls():
    k=uuid4().hex[:9]
    dep,other="corr_a_"+k,"corr_b_"+k
    manager,worker,approver,outsider=[p+k for p in ("corr_m_","corr_w_","corr_a_","corr_o_")]
    role="role_corr_"+k
    flow,version,first,last,step=[p+k for p in ("flow_","ver_","state_","end_","step_")]
    conv,sess,origin=[p+k for p in ("conv_","sess_","wrk_")]
    case_id=None
    new_work=None
    with psycopg.connect(settings.DATABASE_URL,autocommit=True) as conn:
        with conn.cursor() as cur:
            for d in (dep,other):
                cur.execute("INSERT INTO security.departments(id,code,name) VALUES(%s,%s,%s)",
                            (d,d.upper(),d))
            cur.execute("INSERT INTO security.roles(id,name,permission_set) VALUES(%s,'employee','{}'::jsonb)",(role,))
            for u,d in ((manager,dep),(worker,dep),(approver,dep),(outsider,other)):
                cur.execute("""INSERT INTO security.users(id,email,hashed_password,department_id)
                    VALUES(%s,%s,'synthetic',%s)""",(u,u+"@example.test",d))
            cur.execute("INSERT INTO security.user_roles(user_id,role_id) VALUES(%s,%s)",(worker,role))
            cur.execute("""INSERT INTO knowledge_studio.workflows
                (id,workflow_code,title,department_id,category,created_by)
                VALUES(%s,%s,'Corrective receiving SOP',%s,'receiving',%s)""",
                (flow,"CORRECTIVE_"+k.upper(),dep,manager))
            cur.execute("""INSERT INTO knowledge_studio.workflow_versions
                (id,workflow_id,version_number,stage_file_uri,ast_hash,status,published_at)
                VALUES(%s,%s,1,'pgobj:corrective',%s,'published',CURRENT_TIMESTAMP)""",
                (version,flow,"b"*64))
            for state,typ,initial,terminal,n in (
                (first,"ATOMIC_STEP",True,False,1),(last,"END",False,True,2)
            ):
                cur.execute("""INSERT INTO knowledge_studio.workflow_states
                    (id,workflow_version_id,state_key,state_type,title,is_initial,is_terminal,ordinal_index)
                    VALUES(%s,%s,%s,%s,'Corrective inspection',%s,%s,%s)""",
                    (state,version,state,typ,initial,terminal,n))
            cur.execute("""INSERT INTO knowledge_studio.workflow_steps
                (id,state_id,step_code,instruction,expected_output_type,is_mandatory,ordinal_index)
                VALUES(%s,%s,'VERIFY_SEAL','Inspect isolated carton seals','CONFIRMATION',TRUE,1)""",
                (step,first))
            cur.execute("""INSERT INTO workmate_copilot.conversations(id,user_id,department_id)
                VALUES(%s,%s,%s)""",(conv,worker,dep))
            cur.execute("""INSERT INTO workmate_copilot.workflow_sessions
                (id,conversation_id,workflow_version_id,current_state_id,user_id,status,session_context)
                VALUES(%s,%s,%s,%s,%s,'paused','{}'::jsonb)""",
                (sess,conv,version,first,worker))
            cur.execute("""INSERT INTO workmate_copilot.work_items
                (id,department_id,created_by,assigned_to,title,work_type,priority,status,
                 workflow_version_id,execution_session_id)
                VALUES(%s,%s,%s,%s,'Inspect held cartons','receiving','high','blocked',%s,%s)""",
                (origin,dep,manager,worker,version,sess))
    try:
        with psycopg.connect(settings.DATABASE_URL) as conn:
            with conn.cursor() as cur:
                cur.execute("BEGIN")
                cur.execute("SELECT set_config('workmate.department_id',%s,true)",(dep,))
                case_id=open_case(cur,{"id":origin,"status":"blocked","execution_session_id":sess},
                                  dep,worker,"worker_report","Damaged carton needs separate QA.")
                cur.execute("COMMIT")
        claimed=WorkExceptionRepository.claim(dep,manager,case_id,1)
        assert claimed["revision"]==2
        reviewed=WorkExceptionRepository.review(
            dep,manager,case_id,2,"reviewed",
            "Continue isolation and require independent QA verification."
        )
        assert reviewed["revision"]==3
        assert WorkExceptionRepository.action(
            dep,manager,case_id,3,"containment_recorded",
            "Affected cartons remain isolated in receiving bay four."
        )["revision"]==4
        assert WorkExceptionRepository.action(
            dep,manager,case_id,4,"remediation_proposed",
            "Separate employee will inspect carton seals using a published SOP."
        )["revision"]==5
        with pytest.raises(CaseNotFound):
            CorrectiveWorkRepository.request(other,outsider,case_id,5,version,worker,
                "Request to bypass other department.")
        with pytest.raises(CaseConflict):
            CorrectiveWorkRepository.request(dep,worker,case_id,5,version,worker,
                "Worker may not create independent corrective work.")
        with pytest.raises(CaseConflict):
            CorrectiveWorkRepository.request(dep,manager,case_id,5,"not_published",worker,
                "Must use published SOP in this department.")
        plan=CorrectiveWorkRepository.request(
            dep,manager,case_id,5,version,worker,
            "Reinspect held cartons with a separately recorded checklist and new evidence."
        )
        assert plan["status"]=="pending"
        # Reviewed cases remain visible to supervisors when a separate
        # administrator still needs to authorize corrective verification.
        queue=WorkExceptionRepository.list(dep)
        pending=next(item for item in queue if item["id"]==case_id)
        assert pending["corrective_status"]=="pending"
        request_id=plan["id"]
        with pytest.raises(CaseConflict):
            CorrectiveWorkRepository.request(dep,manager,case_id,6,version,worker,
                "Replay should never issue another corrective request.")
        with pytest.raises(CaseConflict):
            CorrectiveWorkRepository.decide(dep,manager,case_id,request_id,"approved",
                "Self approval cannot create new corrective work.")
        with pytest.raises(CaseConflict):
            CorrectiveWorkRepository.decide(dep,worker,case_id,request_id,"approved",
                "Worker must not approve own incident.")
        with pytest.raises(CaseNotFound):
            CorrectiveWorkRepository.decide(other,outsider,case_id,request_id,"approved",
                "No foreign approvals may be accepted.")
        approval=CorrectiveWorkRepository.decide(
            dep,approver,case_id,request_id,"approved",
            "Independent desk authorization for a new task; original physical hold stays in place."
        )
        new_work=approval["corrective_work_id"]
        assert approval["status"]=="approved" and new_work.startswith("wrk_")
        with pytest.raises(CaseConflict):
            CorrectiveWorkRepository.decide(dep,approver,case_id,request_id,"approved",
                "Replay of authorization is prohibited.")
        record=WorkExceptionRepository.get(dep,case_id)
        assert record["corrective_request"]["corrective_work_id"]==new_work
        assert record["corrective_request"]["decided_by"]==approver
        assert record["work_status"]=="blocked"
        position=WorkExecutionRepository.position(dep,worker,False,new_work)
        assert position["status"]=="ready"
        assert position["workflow_version_id"]==version
        with psycopg.connect(settings.DATABASE_URL) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT status FROM workmate_copilot.workflow_sessions WHERE id=%s",(sess,))
                assert cur.fetchone()[0]=="paused"
                cur.execute("SELECT status FROM workmate_copilot.work_items WHERE id=%s",(origin,))
                assert cur.fetchone()[0]=="blocked"
                cur.execute("BEGIN")
                cur.execute("SET LOCAL ROLE workmate_scoped_reader")
                cur.execute("SELECT COUNT(*) FROM workmate_copilot.work_corrective_requests WHERE id=%s",(request_id,))
                assert cur.fetchone()[0]==0
                cur.execute("SELECT set_config('workmate.department_id',%s,true)",(other,))
                cur.execute("SELECT COUNT(*) FROM workmate_copilot.work_corrective_requests WHERE id=%s",(request_id,))
                assert cur.fetchone()[0]==0
                cur.execute("SELECT set_config('workmate.department_id',%s,true)",(dep,))
                cur.execute("SELECT COUNT(*) FROM workmate_copilot.work_corrective_requests WHERE id=%s",(request_id,))
                assert cur.fetchone()[0]==1
                cur.execute("ROLLBACK")
    finally:
        with psycopg.connect(settings.DATABASE_URL,autocommit=True) as conn:
            with conn.cursor() as cur:
                if case_id:
                    cur.execute("DELETE FROM workmate_copilot.work_item_events WHERE work_item_id IN (%s,%s)",(origin,new_work or origin))
                    cur.execute("DELETE FROM workmate_copilot.work_corrective_requests WHERE case_id=%s",(case_id,))
                    cur.execute("DELETE FROM workmate_copilot.work_exception_events WHERE case_id=%s",(case_id,))
                    cur.execute("DELETE FROM workmate_copilot.work_exceptions WHERE id=%s",(case_id,))
                if new_work:
                    cur.execute("DELETE FROM workmate_copilot.work_items WHERE id=%s",(new_work,))
                cur.execute("DELETE FROM workmate_copilot.work_items WHERE id=%s",(origin,))
                cur.execute("DELETE FROM workmate_copilot.workflow_sessions WHERE id=%s",(sess,))
                cur.execute("DELETE FROM workmate_copilot.conversations WHERE id=%s",(conv,))
                cur.execute("DELETE FROM knowledge_studio.workflow_steps WHERE id=%s",(step,))
                cur.execute("DELETE FROM knowledge_studio.workflow_states WHERE workflow_version_id=%s",(version,))
                cur.execute("DELETE FROM knowledge_studio.workflow_versions WHERE id=%s",(version,))
                cur.execute("DELETE FROM knowledge_studio.workflows WHERE id=%s",(flow,))
                cur.execute("DELETE FROM security.user_roles WHERE role_id=%s",(role,))
                cur.execute("DELETE FROM security.users WHERE id=ANY(%s)",([manager,worker,approver,outsider],))
                cur.execute("DELETE FROM security.roles WHERE id=%s",(role,))
                cur.execute("DELETE FROM security.departments WHERE id=ANY(%s)",([dep,other],))
