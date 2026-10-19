"""Actual disposable PostgreSQL acceptance: compiled SOP, evidence and task state."""
from __future__ import annotations
import base64
from uuid import uuid4
import psycopg
import pytest
from app.core.config import settings
from app.repositories.work_item_repository import WorkItemRepository
from app.repositories.work_execution_repository import WorkExecutionRepository,ExecutionConflict,ExecutionNotFound
from app.repositories.workflow_session_repository import WorkflowSessionRepository
from app.exceptions.custom_exceptions import DatabaseException


@pytest.mark.live_integration
def test_sop_binding_step_attestation_evidence_decision_and_tenant_rls():
    k=uuid4().hex[:8]
    department,foreign="ex_a_"+k,"ex_b_"+k
    manager,worker,outsider="ex_mgr_"+k,"ex_emp_"+k,"ex_out_"+k
    role="ex_role_"+k
    workflow="sop_w_"+k
    version="sop_v_"+k
    state="sop_s_"+k
    decision="sop_d_"+k
    end="sop_e_"+k
    first,second="sop_p_"+k,"sop_q_"+k
    spec="sop_spec_"+k
    task_id=None
    with psycopg.connect(settings.DATABASE_URL,autocommit=True) as conn:
        with conn.cursor() as cur:
            for dep in (department,foreign):
                cur.execute("INSERT INTO security.departments(id,code,name) VALUES(%s,%s,%s)",(dep,dep.upper(),dep))
            cur.execute("INSERT INTO security.roles(id,name,permission_set) VALUES(%s,'employee','{}'::jsonb)",(role,))
            for actor,dep in ((manager,department),(worker,department),(outsider,foreign)):
                cur.execute("""INSERT INTO security.users(id,email,hashed_password,department_id)
                    VALUES(%s,%s,'synthetic',%s)""",(actor,actor+"@example.test",dep))
            cur.execute("INSERT INTO security.user_roles(user_id,role_id) VALUES(%s,%s)",(worker,role))
            cur.execute("""INSERT INTO knowledge_studio.workflows
                (id,workflow_code,title,department_id,category,created_by)
                VALUES(%s,%s,'Controlled Receiving SOP',%s,'receiving',%s)""",
                (workflow,"REC-"+k,department,manager))
            cur.execute("""INSERT INTO knowledge_studio.workflow_versions
                (id,workflow_id,version_number,stage_file_uri,ast_hash,status,published_at)
                VALUES(%s,%s,1,%s,%s,'published',CURRENT_TIMESTAMP)""",
                (version,workflow,"pgobj:"+k,"a"*64))
            for id_,typ,initial,terminal,order in (
                (state,"ATOMIC_STEP",True,False,1),
                (decision,"DECISION",False,False,2),
                (end,"END",False,True,3),
            ):
                cur.execute("""INSERT INTO knowledge_studio.workflow_states
                    (id,workflow_version_id,state_key,state_type,title,is_initial,is_terminal,ordinal_index)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (id_,version,id_,typ,"Inspect receiving" if id_==state else
                     "Operator decision" if id_==decision else "Complete",initial,terminal,order))
            for step_id,output_type,index in ((first,"CONFIRMATION",1),(second,"TEXT_INPUT",2)):
                cur.execute("""INSERT INTO knowledge_studio.workflow_steps
                   (id,state_id,step_code,instruction,expected_output_type,is_mandatory,ordinal_index)
                   VALUES(%s,%s,%s,%s,%s,TRUE,%s)""",
                   (step_id,state,step_id,"Inspect seal" if index==1 else "Record carton details",
                    output_type,index))
            cur.execute("""INSERT INTO knowledge_studio.workflow_evidence_specs
                (id,step_id,evidence_type,min_size_bytes,is_required)
                VALUES(%s,%s,'PHOTO_JPEG',6,TRUE)""",(spec,second))
            cur.execute("""INSERT INTO knowledge_studio.workflow_transitions
                (id,from_state_id,to_state_id,condition_type,condition_expression)
                VALUES(%s,%s,%s,'ALWAYS',NULL)""",("tr_a_"+k,state,decision))
            cur.execute("""INSERT INTO knowledge_studio.workflow_transitions
                (id,from_state_id,to_state_id,condition_type,condition_expression)
                VALUES(%s,%s,%s,'DECISION_OPTION','ACCEPT')""",
                ("tr_b_"+k,decision,end))
            cur.execute("""INSERT INTO knowledge_studio.workflow_decision_options
                (id,state_id,option_code,option_label,target_state_id)
                VALUES(%s,%s,'ACCEPT','Accept and finish',%s)""",
                ("opt_"+k,decision,end))
    try:
        task=WorkItemRepository.create(
            department,manager,"Inspect inbound shipment for approved procedure",
            "receiving","high","Keep seal evidence.","INB-"+k,worker)
        assert task["status"]=="queued"
        task_id=task["id"]
        assert any(p["workflow_version_id"]==version
                   for p in WorkExecutionRepository.procedures(department))
        with pytest.raises(ExecutionConflict):
            WorkExecutionRepository.bind(department,manager,task_id,"version_from_other_department")
        ready=WorkExecutionRepository.bind(department,manager,task_id,version)
        assert ready["status"]=="ready"
        with pytest.raises(ExecutionConflict):
            WorkExecutionRepository.bind(department,manager,task_id,version)
        with pytest.raises(ExecutionNotFound):
            WorkExecutionRepository.start(foreign,outsider,task_id)
        started=WorkExecutionRepository.start(department,worker,task_id)
        assert started["status"]=="active" and started["step"]["id"]==first
        assert started["total_steps"]==2
        session=started["session_id"]
        with pytest.raises(ExecutionConflict):
            WorkExecutionRepository.start(department,worker,task_id)
        with pytest.raises(ExecutionNotFound):
            WorkExecutionRepository.position(department,manager,False,task_id)
        assert WorkExecutionRepository.position(department,manager,True,task_id)["status"]=="active"
        paused=WorkExecutionRepository.change_status(department,worker,task_id,"pause")
        assert paused["status"]=="paused"
        with pytest.raises(ExecutionConflict):
            WorkExecutionRepository.progress(department,worker,task_id,first,True,"",None,[])
        resumed=WorkExecutionRepository.change_status(department,worker,task_id,"resume")
        assert resumed["status"]=="active"
        with pytest.raises(ExecutionConflict):
            WorkExecutionRepository.progress(department,worker,task_id,first,False,"",None,[])
        step1=WorkExecutionRepository.progress(department,worker,task_id,first,True,"",None,[])
        assert step1["completed_steps"]==1 and step1["step"]["id"]==second
        with pytest.raises(ExecutionConflict):
            WorkExecutionRepository.progress(department,worker,task_id,first,True,"",None,[])
        with pytest.raises(ExecutionConflict):
            WorkExecutionRepository.progress(department,worker,task_id,second,False,"Carton checked",None,[])
        bad=[{"spec_id":spec,"filename":"inspection.jpg",
              "content_base64":base64.b64encode(b"not-a-jpeg").decode()}]
        with pytest.raises(ExecutionConflict):
            WorkExecutionRepository.progress(department,worker,task_id,second,False,"Carton checked",None,bad)
        with psycopg.connect(settings.DATABASE_URL) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT count(*) FROM workmate_copilot.workflow_step_executions WHERE session_id=%s",(session,))
                assert cur.fetchone()==(1,), "Rejected evidence must leave no extra step record"
        jpeg=[{"spec_id":spec,"filename":"inspection.jpg",
               "content_base64":base64.b64encode(b"\xff\xd8\xffsynthetic-carton-bytes").decode()}]
        step2=WorkExecutionRepository.progress(department,worker,task_id,second,False,"Carton checked",None,jpeg)
        assert step2["completed_steps"]==2 and step2["step"] is None
        assert step2["decision_options"][0]["option_code"]=="ACCEPT"
        with pytest.raises(ExecutionConflict):
            WorkExecutionRepository.decide(department,worker,task_id,"UNKNOWN")
        done=WorkExecutionRepository.decide(department,worker,task_id,"ACCEPT")
        assert done["status"]=="completed"
        with pytest.raises(ExecutionConflict):
            WorkExecutionRepository.decide(department,worker,task_id,"ACCEPT")
        with pytest.raises(DatabaseException):
            WorkflowSessionRepository.apply_progress(session,state,None,{})
        with pytest.raises(DatabaseException):
            WorkflowSessionRepository.update_status(session,"active","paused",{})
        log=WorkExecutionRepository.timeline(department,worker,False,task_id)
        assert [e["action"] for e in log]==[
            "created","bound","started","paused","resumed",
            "step_recorded","step_recorded","decision_recorded","completed"]
        with psycopg.connect(settings.DATABASE_URL) as conn:
            with conn.cursor() as cur:
                cur.execute("""SELECT verification_status,stage_file_uri
                     FROM workmate_copilot.workflow_evidence_submissions""")
                files=cur.fetchall()
                assert ("RECEIVED_UNVERIFIED",files[-1][1]) in files
                cur.execute("BEGIN")
                cur.execute("SET LOCAL ROLE workmate_scoped_reader")
                cur.execute("SELECT count(*) FROM workmate_copilot.work_items WHERE id=%s",(task_id,))
                assert cur.fetchone()==(0,)
                cur.execute("SELECT set_config('workmate.department_id',%s,true)",(foreign,))
                cur.execute("SELECT count(*) FROM workmate_copilot.work_items WHERE id=%s",(task_id,))
                assert cur.fetchone()==(0,)
                cur.execute("SELECT set_config('workmate.department_id',%s,true)",(department,))
                cur.execute("SELECT count(*) FROM workmate_copilot.work_items WHERE id=%s",(task_id,))
                assert cur.fetchone()==(1,)
                cur.execute("ROLLBACK")
    finally:
        with psycopg.connect(settings.DATABASE_URL,autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute("""SELECT e.stage_file_uri FROM workmate_copilot.workflow_evidence_submissions e
                    JOIN workmate_copilot.workflow_step_executions x ON e.step_execution_id=x.id
                    JOIN workmate_copilot.workflow_sessions s ON x.session_id=s.id
                    WHERE s.workflow_version_id=%s""",(version,))
                source_ids=[row[0][6:] for row in cur.fetchall() if row[0].startswith("pgobj:")]
                cur.execute("""DELETE FROM workmate_copilot.workflow_evidence_submissions
                    WHERE step_execution_id IN (SELECT x.id FROM workmate_copilot.workflow_step_executions x
                    JOIN workmate_copilot.workflow_sessions s ON s.id=x.session_id
                    WHERE s.workflow_version_id=%s)""",(version,))
                cur.execute("""DELETE FROM workmate_copilot.workflow_step_executions
                    WHERE session_id IN (SELECT id FROM workmate_copilot.workflow_sessions
                    WHERE workflow_version_id=%s)""",(version,))
                if task_id:
                    cur.execute("DELETE FROM workmate_copilot.work_item_events WHERE work_item_id=%s",(task_id,))
                    cur.execute("DELETE FROM workmate_copilot.work_items WHERE id=%s",(task_id,))
                cur.execute("DELETE FROM workmate_copilot.workflow_sessions WHERE workflow_version_id=%s",(version,))
                cur.execute("DELETE FROM workmate_copilot.conversations WHERE user_id=%s",(worker,))
                if source_ids:
                    cur.execute("DELETE FROM shared.source_objects WHERE id=ANY(%s)",(source_ids,))
                cur.execute("DELETE FROM knowledge_studio.workflow_decision_options WHERE state_id=%s",(decision,))
                cur.execute("DELETE FROM knowledge_studio.workflow_transitions WHERE from_state_id=ANY(%s)",([state,decision],))
                cur.execute("DELETE FROM knowledge_studio.workflow_evidence_specs WHERE step_id=%s",(second,))
                cur.execute("DELETE FROM knowledge_studio.workflow_steps WHERE state_id=%s",(state,))
                cur.execute("DELETE FROM knowledge_studio.workflow_states WHERE workflow_version_id=%s",(version,))
                cur.execute("DELETE FROM knowledge_studio.workflow_versions WHERE id=%s",(version,))
                cur.execute("DELETE FROM knowledge_studio.workflows WHERE id=%s",(workflow,))
                cur.execute("DELETE FROM security.user_roles WHERE role_id=%s",(role,))
                cur.execute("DELETE FROM security.users WHERE id=ANY(%s)",([manager,worker,outsider],))
                cur.execute("DELETE FROM security.roles WHERE id=%s",(role,))
                cur.execute("DELETE FROM security.departments WHERE id=ANY(%s)",([department,foreign],))
