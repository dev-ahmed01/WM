"""Phase 4D disposable PostgreSQL acceptance: evidence review, site separation and hold."""
import base64
import io
from uuid import uuid4

import psycopg
import pytest
from PIL import Image

from app.core.config import settings
from app.repositories.work_exception_repository import (
    WorkExceptionRepository, open_case, CaseConflict, CaseNotFound,
)
from app.repositories.work_corrective_repository import CorrectiveWorkRepository
from app.repositories.work_case_closure_repository import CaseClosureRepository
from app.repositories.work_execution_repository import WorkExecutionRepository


@pytest.mark.live_integration
def test_case_closure_requires_fresh_corrective_proof_and_independent_site_signer():
    key=uuid4().hex[:9]
    dept,foreign="close_"+key,"foreign_"+key
    manager,worker,approver,site,outsider=[
        prefix+key for prefix in ("close_m_","close_w_","close_a_","close_s_","close_o_")
    ]
    role_emp,role_admin="close_emp_"+key,"close_admin_"+key
    flow,version,initial,terminal,step,spec,edge=[
        prefix+key for prefix in ("cf_","cv_","cs_","ct_","cp_","ce_","cx_")
    ]
    original_conv,original_session,original_work=[
        prefix+key for prefix in ("cc_","cse_","cw_")
    ]
    case_id=None
    corrective_work=None
    fresh_session=None
    fresh_conversation=None
    with psycopg.connect(settings.DATABASE_URL,autocommit=True) as conn:
        with conn.cursor() as cur:
            for d in (dept,foreign):
                cur.execute("INSERT INTO security.departments(id,code,name) VALUES(%s,%s,%s)",(d,d.upper(),d))
            for role,name in ((role_emp,"employee"),(role_admin,"admin")):
                cur.execute("""INSERT INTO security.roles(id,name,permission_set)
                    VALUES(%s,%s,'{}'::jsonb)""",(role,name))
            for actor,d in ((manager,dept),(worker,dept),(approver,dept),(site,dept),(outsider,foreign)):
                cur.execute("""INSERT INTO security.users(id,email,hashed_password,department_id,status)
                    VALUES(%s,%s,'fixture',%s,'active')""",(actor,actor+"@example.test",d))
            for actor,role in ((worker,role_emp),(approver,role_admin),(site,role_admin)):
                cur.execute("INSERT INTO security.user_roles(user_id,role_id) VALUES(%s,%s)",(actor,role))
            cur.execute("""INSERT INTO knowledge_studio.workflows
                (id,workflow_code,title,department_id,category,created_by)
                VALUES(%s,%s,'Corrective carton verification',%s,'receiving',%s)""",
                (flow,"CLOSE_"+key.upper(),dept,manager))
            cur.execute("""INSERT INTO knowledge_studio.workflow_versions
                (id,workflow_id,version_number,stage_file_uri,ast_hash,status,published_at)
                VALUES(%s,%s,1,'pgobj:closure_fixture',%s,'published',CURRENT_TIMESTAMP)""",
                (version,flow,"c"*64))
            for state,kind,first,last,index in (
                (initial,"ATOMIC_STEP",True,False,1),(terminal,"END",False,True,2)
            ):
                cur.execute("""INSERT INTO knowledge_studio.workflow_states
                    (id,workflow_version_id,state_key,state_type,title,is_initial,is_terminal,ordinal_index)
                    VALUES(%s,%s,%s,%s,'Check isolated cartons',%s,%s,%s)""",
                    (state,version,state,kind,first,last,index))
            cur.execute("""INSERT INTO knowledge_studio.workflow_steps
                (id,state_id,step_code,instruction,expected_output_type,is_mandatory,ordinal_index)
                VALUES(%s,%s,'CHECK_PHOTO','Record carton inspection','CONFIRMATION',TRUE,1)""",
                (step,initial))
            cur.execute("""INSERT INTO knowledge_studio.workflow_evidence_specs
                (id,step_id,evidence_type,is_required,min_size_bytes)
                VALUES(%s,%s,'PHOTO_JPEG',TRUE,6)""",(spec,step))
            cur.execute("""INSERT INTO knowledge_studio.workflow_transitions
                (id,from_state_id,to_state_id,condition_type)
                VALUES(%s,%s,%s,'ALWAYS')""",(edge,initial,terminal))
            cur.execute("""INSERT INTO workmate_copilot.conversations(id,user_id,department_id)
                VALUES(%s,%s,%s)""",(original_conv,worker,dept))
            cur.execute("""INSERT INTO workmate_copilot.workflow_sessions
                (id,conversation_id,workflow_version_id,current_state_id,user_id,status,session_context)
                VALUES(%s,%s,%s,%s,%s,'paused','{}'::jsonb)""",
                (original_session,original_conv,version,initial,worker))
            cur.execute("""INSERT INTO workmate_copilot.work_items
                (id,department_id,created_by,assigned_to,title,work_type,priority,status,
                 workflow_version_id,execution_session_id)
                VALUES(%s,%s,%s,%s,'Original held receipt','receiving','high','blocked',%s,%s)""",
                (original_work,dept,manager,worker,version,original_session))
    try:
        with psycopg.connect(settings.DATABASE_URL) as conn:
            with conn.cursor() as cur:
                cur.execute("BEGIN")
                cur.execute("SELECT set_config('workmate.department_id',%s,true)",(dept,))
                case_id=open_case(cur,{"id":original_work,"status":"blocked",
                    "execution_session_id":original_session},dept,worker,
                    "worker_report","Quarantined cartons require QA inspection.")
                cur.execute("COMMIT")
        WorkExceptionRepository.claim(dept,manager,case_id,1)
        WorkExceptionRepository.review(dept,manager,case_id,2,"reviewed",
            "The cartons are isolated pending independent corrective proof.")
        WorkExceptionRepository.action(dept,manager,case_id,3,"containment_recorded",
            "Held cartons quarantined with bay owner notified.")
        WorkExceptionRepository.action(dept,manager,case_id,4,"remediation_proposed",
            "Separate worker will reinspect carton and submit photographic proof.")
        req=CorrectiveWorkRepository.request(dept,manager,case_id,5,version,worker,
            "Verify carton condition with published SOP and retain a new photograph.")
        approved=CorrectiveWorkRepository.decide(dept,approver,case_id,req["id"],"approved",
            "Authorize a separate corrective task; the original hold remains unchanged.")
        corrective_work=approved["corrective_work_id"]
        assert WorkExceptionRepository.get(dept,case_id)["revision"]==7
        with pytest.raises(CaseNotFound):
            CaseClosureRepository.review_evidence(foreign,outsider,case_id,7,
                "Cross-department reviewer must never see this case.")
        with pytest.raises(CaseConflict):
            CaseClosureRepository.review_evidence(dept,manager,case_id,7,
                "There is no completed SOP or evidence yet.")
        started=WorkExecutionRepository.start(dept,worker,corrective_work)
        fresh_session=started["session_id"]
        with psycopg.connect(settings.DATABASE_URL) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT conversation_id FROM workmate_copilot.workflow_sessions WHERE id=%s",(fresh_session,))
                fresh_conversation=cur.fetchone()[0]
        photo=io.BytesIO()
        Image.new("RGB",(32,32)).save(photo,format="JPEG")
        completed=WorkExecutionRepository.progress(
            dept,worker,corrective_work,step,True,"",None,
            [{"spec_id":spec,"filename":"corrective.jpg",
              "content_base64":base64.b64encode(photo.getvalue()).decode("ascii")}],
        )
        assert completed["status"]=="completed"
        with pytest.raises(CaseConflict):
            CaseClosureRepository.review_evidence(dept,worker,case_id,7,
                "Original reporting worker is not an independent case supervisor.")
        reviewed=CaseClosureRepository.review_evidence(dept,manager,case_id,7,
            "Reviewed the completed corrective SOP and attached new photo submission.")
        assert reviewed["evidence_snapshot"]["recorded_step_count"]==1
        assert len(reviewed["evidence_snapshot"]["received_evidence"])==1
        assert reviewed["evidence_snapshot"]["physical_inspection_verified_by_system"] is False
        assert WorkExceptionRepository.get(dept,case_id)["revision"]==8
        with pytest.raises(CaseConflict):
            CaseClosureRepository.review_evidence(dept,manager,case_id,7,
                "Replay must not replace previously reviewed evidence.")
        kwargs=(case_id,8,"QA-SITE-CHECK-2071",
            "An independent on-site inspector checked quarantined receiving bay evidence.",True)
        with pytest.raises(CaseConflict):
            CaseClosureRepository.accept_site(dept,approver,*kwargs)
        with pytest.raises(CaseConflict):
            CaseClosureRepository.accept_site(dept,manager,*kwargs)
        with pytest.raises(CaseConflict):
            CaseClosureRepository.accept_site(dept,worker,*kwargs)
        with pytest.raises(CaseNotFound):
            CaseClosureRepository.accept_site(foreign,outsider,*kwargs)
        with pytest.raises(CaseConflict):
            CaseClosureRepository.accept_site(dept,site,case_id,8,"QA-SITE-CHECK-2071",
                kwargs[-2],False)
        closed=CaseClosureRepository.accept_site(dept,site,*kwargs)
        assert closed["status"]=="closed" and closed["original_work_status"]=="blocked"
        assert WorkExceptionRepository.get(dept,case_id)["closure"]["site_accepted_by"]==site
        with pytest.raises(CaseConflict):
            CaseClosureRepository.accept_site(dept,site,*kwargs)
        assert WorkExecutionRepository.position(dept,worker,False,original_work)["status"]=="blocked"
        with psycopg.connect(settings.DATABASE_URL) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT status FROM workmate_copilot.workflow_sessions WHERE id=%s",(original_session,))
                assert cur.fetchone()[0]=="paused"
                cur.execute("BEGIN")
                cur.execute("SET LOCAL ROLE workmate_scoped_reader")
                cur.execute("SELECT COUNT(*) FROM workmate_copilot.work_case_closures WHERE case_id=%s",(case_id,))
                assert cur.fetchone()[0]==0
                cur.execute("SELECT set_config('workmate.department_id',%s,true)",(foreign,))
                cur.execute("SELECT COUNT(*) FROM workmate_copilot.work_case_closures WHERE case_id=%s",(case_id,))
                assert cur.fetchone()[0]==0
                cur.execute("SELECT set_config('workmate.department_id',%s,true)",(dept,))
                cur.execute("SELECT COUNT(*) FROM workmate_copilot.work_case_closures WHERE case_id=%s",(case_id,))
                assert cur.fetchone()[0]==1
                cur.execute("ROLLBACK")
    finally:
        with psycopg.connect(settings.DATABASE_URL,autocommit=True) as conn:
            with conn.cursor() as cur:
                if case_id:
                    cur.execute("DELETE FROM workmate_copilot.work_case_closures WHERE case_id=%s",(case_id,))
                    cur.execute("DELETE FROM workmate_copilot.work_corrective_requests WHERE case_id=%s",(case_id,))
                    cur.execute("DELETE FROM workmate_copilot.work_exception_events WHERE case_id=%s",(case_id,))
                    cur.execute("DELETE FROM workmate_copilot.work_exceptions WHERE id=%s",(case_id,))
                if corrective_work:
                    cur.execute("""DELETE FROM workmate_copilot.workflow_evidence_submissions
                      WHERE step_execution_id IN (SELECT id FROM workmate_copilot.workflow_step_executions
                                                  WHERE session_id=%s)""",(fresh_session,))
                    cur.execute("DELETE FROM workmate_copilot.workflow_step_executions WHERE session_id=%s",(fresh_session,))
                    cur.execute("DELETE FROM workmate_copilot.work_item_events WHERE work_item_id=%s",(corrective_work,))
                    cur.execute("DELETE FROM workmate_copilot.work_items WHERE id=%s",(corrective_work,))
                    cur.execute("DELETE FROM workmate_copilot.workflow_sessions WHERE id=%s",(fresh_session,))
                    cur.execute("DELETE FROM workmate_copilot.conversations WHERE id=%s",(fresh_conversation,))
                    cur.execute("DELETE FROM shared.source_objects WHERE department_id=%s",(dept,))
                cur.execute("DELETE FROM workmate_copilot.work_item_events WHERE work_item_id=%s",(original_work,))
                cur.execute("DELETE FROM workmate_copilot.work_items WHERE id=%s",(original_work,))
                cur.execute("DELETE FROM workmate_copilot.workflow_sessions WHERE id=%s",(original_session,))
                cur.execute("DELETE FROM workmate_copilot.conversations WHERE id=%s",(original_conv,))
                cur.execute("DELETE FROM knowledge_studio.workflow_transitions WHERE id=%s",(edge,))
                cur.execute("DELETE FROM knowledge_studio.workflow_evidence_specs WHERE id=%s",(spec,))
                cur.execute("DELETE FROM knowledge_studio.workflow_steps WHERE id=%s",(step,))
                cur.execute("DELETE FROM knowledge_studio.workflow_states WHERE workflow_version_id=%s",(version,))
                cur.execute("DELETE FROM knowledge_studio.workflow_versions WHERE id=%s",(version,))
                cur.execute("DELETE FROM knowledge_studio.workflows WHERE id=%s",(flow,))
                cur.execute("DELETE FROM security.user_roles WHERE role_id IN (%s,%s)",(role_emp,role_admin))
                cur.execute("DELETE FROM security.users WHERE id=ANY(%s)",([manager,worker,approver,site,outsider],))
                cur.execute("DELETE FROM security.roles WHERE id IN (%s,%s)",(role_emp,role_admin))
                cur.execute("DELETE FROM security.departments WHERE id=ANY(%s)",([dept,foreign],))
