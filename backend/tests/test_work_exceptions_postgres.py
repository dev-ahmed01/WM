"""Phase 4A actual PostgreSQL case lifecycle and department RLS acceptance."""
from uuid import uuid4
import psycopg
import pytest
from app.core.config import settings
from app.repositories.work_exception_repository import (
    WorkExceptionRepository,open_case,CaseNotFound,CaseConflict,
)

@pytest.mark.live_integration
def test_work_exception_claim_review_isolated_and_never_releases_work():
    suffix=uuid4().hex[:9]
    dept,other="case_a_"+suffix,"case_b_"+suffix
    manager,worker,outsider="case_m_"+suffix,"case_w_"+suffix,"case_x_"+suffix
    workflow,version,state="case_sop_"+suffix,"case_ver_"+suffix,"case_st_"+suffix
    conversation,session="case_conv_"+suffix,"case_sess_"+suffix
    task="case_task_"+suffix
    case=None
    with psycopg.connect(settings.DATABASE_URL,autocommit=True) as conn:
        with conn.cursor() as cur:
            for d in (dept,other):
                cur.execute("INSERT INTO security.departments(id,code,name) VALUES(%s,%s,%s)",
                            (d,d.upper(),d))
            for actor,d in ((manager,dept),(worker,dept),(outsider,other)):
                cur.execute("""INSERT INTO security.users(id,email,hashed_password,department_id)
                    VALUES (%s,%s,'synthetic',%s)""",(actor,actor+"@example.test",d))
            cur.execute("""INSERT INTO knowledge_studio.workflows
                (id,workflow_code,title,department_id,category,created_by)
                VALUES(%s,%s,'Receiving hold',%s,'receiving',%s)""",
                (workflow,"CASE_"+suffix.upper(),dept,manager))
            cur.execute("""INSERT INTO knowledge_studio.workflow_versions
                (id,workflow_id,version_number,stage_file_uri,ast_hash,status,published_at)
                VALUES(%s,%s,1,'pgobj:synthetic',%s,'published',CURRENT_TIMESTAMP)""",
                (version,workflow,"a"*64))
            cur.execute("""INSERT INTO knowledge_studio.workflow_states
                (id,workflow_version_id,state_key,state_type,title,is_initial,is_terminal,ordinal_index)
                VALUES(%s,%s,'STATE_HOLD','ESCALATION','Supervisor hold',TRUE,FALSE,1)""",
                (state,version))
            cur.execute("""INSERT INTO workmate_copilot.conversations(id,user_id,department_id)
                VALUES(%s,%s,%s)""",(conversation,worker,dept))
            cur.execute("""INSERT INTO workmate_copilot.workflow_sessions
                (id,conversation_id,workflow_version_id,current_state_id,user_id,status,session_context)
                VALUES (%s,%s,%s,%s,%s,'paused','{}'::jsonb)""",
                (session,conversation,version,state,worker))
            cur.execute("""INSERT INTO workmate_copilot.work_items
                (id,department_id,created_by,assigned_to,title,work_type,priority,
                 status,workflow_version_id,execution_session_id)
                VALUES(%s,%s,%s,%s,'Inspect inbound goods','receiving','high',
                       'blocked',%s,%s)""",(task,dept,manager,worker,version,session))
    try:
        with psycopg.connect(settings.DATABASE_URL) as conn:
            with conn.cursor() as cur:
                cur.execute("BEGIN")
                cur.execute("SELECT set_config('workmate.department_id',%s,true)",(dept,))
                case=open_case(cur,{"id":task,"status":"blocked","execution_session_id":session},
                               dept,worker,"sop_outcome","Seal damage requires review.",
                               state,"OPT_DAMAGE")
                with pytest.raises(CaseConflict):
                    open_case(cur,{"id":task,"status":"blocked","execution_session_id":session},
                              dept,worker,"worker_report","Duplicate report.")
                cur.execute("COMMIT")
        assert case.startswith("case_")
        assert WorkExceptionRepository.list(other)==[]
        assert len(WorkExceptionRepository.list(dept))==1
        with pytest.raises(CaseNotFound):
            WorkExceptionRepository.get(other,case)
        details=WorkExceptionRepository.get(dept,case)
        assert details["reason"]=="Seal damage requires review."
        assert [event["action"] for event in details["events"]]==["opened"]
        with pytest.raises(CaseConflict):
            WorkExceptionRepository.claim(dept,worker,case,1)
        with pytest.raises(CaseConflict):
            WorkExceptionRepository.claim(dept,manager,case,99)
        claimed=WorkExceptionRepository.claim(dept,manager,case,1)
        assert claimed["status"]=="claimed" and claimed["revision"]==2
        with pytest.raises(CaseConflict):
            WorkExceptionRepository.claim(dept,outsider,case,2)
        with pytest.raises(CaseConflict):
            WorkExceptionRepository.review(dept,worker,case,2,"reviewed",
                                           "Worker may not review own incident.")
        reviewed=WorkExceptionRepository.review(
            dept,manager,case,2,"follow_up_requested",
            "Hold the receiving goods and inspect photos with the next supervisor."
        )
        assert reviewed["status"]=="follow_up_requested" and reviewed["revision"]==3
        with pytest.raises(CaseConflict):
            WorkExceptionRepository.review(dept,manager,case,2,"reviewed",
                                           "Stale repeat review must not pass.")
        observed=WorkExceptionRepository.get(dept,case)
        assert [row["action"] for row in observed["events"]]==[
            "opened","claimed","follow_up_requested"
        ]
        assert observed["work_status"]=="blocked"
        with psycopg.connect(settings.DATABASE_URL) as conn:
            with conn.cursor() as cur:
                cur.execute("""SELECT status FROM workmate_copilot.workflow_sessions
                    WHERE id=%s""",(session,))
                assert cur.fetchone()[0]=="paused"
                cur.execute("BEGIN")
                cur.execute("SET LOCAL ROLE workmate_scoped_reader")
                cur.execute("SELECT count(*) FROM workmate_copilot.work_exceptions WHERE id=%s",(case,))
                assert cur.fetchone()[0]==0
                cur.execute("SELECT set_config('workmate.department_id',%s,true)",(other,))
                cur.execute("SELECT count(*) FROM workmate_copilot.work_exceptions WHERE id=%s",(case,))
                assert cur.fetchone()[0]==0
                cur.execute("SELECT set_config('workmate.department_id',%s,true)",(dept,))
                cur.execute("SELECT count(*) FROM workmate_copilot.work_exceptions WHERE id=%s",(case,))
                assert cur.fetchone()[0]==1
                cur.execute("ROLLBACK")
    finally:
        with psycopg.connect(settings.DATABASE_URL,autocommit=True) as conn:
            with conn.cursor() as cur:
                if case:
                    cur.execute("DELETE FROM workmate_copilot.work_exception_events WHERE case_id=%s",(case,))
                    cur.execute("DELETE FROM workmate_copilot.work_exceptions WHERE id=%s",(case,))
                cur.execute("DELETE FROM workmate_copilot.work_item_events WHERE work_item_id=%s",(task,))
                cur.execute("DELETE FROM workmate_copilot.work_items WHERE id=%s",(task,))
                cur.execute("DELETE FROM workmate_copilot.workflow_sessions WHERE id=%s",(session,))
                cur.execute("DELETE FROM workmate_copilot.conversations WHERE id=%s",(conversation,))
                cur.execute("DELETE FROM knowledge_studio.workflow_states WHERE id=%s",(state,))
                cur.execute("DELETE FROM knowledge_studio.workflow_versions WHERE id=%s",(version,))
                cur.execute("DELETE FROM knowledge_studio.workflows WHERE id=%s",(workflow,))
                cur.execute("DELETE FROM security.users WHERE id=ANY(%s)",([manager,worker,outsider],))
                cur.execute("DELETE FROM security.departments WHERE id=ANY(%s)",([dept,other],))
