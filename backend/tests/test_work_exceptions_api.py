"""Supervisor case authorization, optimistic claiming and safe error handling."""
from unittest.mock import patch
from fastapi.testclient import TestClient
from app.core.security import create_access_token
from app.main import app
from app.repositories.work_exception_repository import CaseConflict,CaseNotFound

client=TestClient(app)

def auth(role="manager",dept="receiving",actor="supervisor"):
    return {"Authorization":"Bearer "+create_access_token(actor,role,dept)}

def test_case_queue_requires_supervisor_and_department_scope():
    assert client.get("/api/v1/work/exceptions").status_code==401
    assert client.get("/api/v1/work/exceptions",headers=auth("employee")).status_code==403
    with patch("app.api.v1.work_exceptions.WorkExceptionRepository.list",return_value=[]) as items:
        result=client.get("/api/v1/work/exceptions?limit=100",headers=auth())
    assert result.status_code==200 and result.json()["items"]==[]
    assert items.call_args.args==("receiving",100)


def test_employee_cannot_view_or_review_incident_even_if_own_task():
    url="/api/v1/work/exceptions/case_one"
    for method,tail,payload in [
        ("get","",None),("post","/claim",{"expected_revision":1}),
        ("post","/review",{"expected_revision":1,"decision":"reviewed",
                           "review_note":"Reviewed reported seal damage."}),
    ]:
        response=getattr(client,method)(url+tail,headers=auth("employee"),
                                        **({"json":payload} if payload else {}))
        assert response.status_code==403


def test_claim_and_review_require_literal_decision_and_expected_revision():
    path="/api/v1/work/exceptions/case_one"
    with patch("app.api.v1.work_exceptions.WorkExceptionRepository.claim",
               return_value={"id":"case_one","revision":2,"status":"claimed"}) as claim:
        result=client.post(path+"/claim",headers=auth(),json={"expected_revision":1})
    assert result.status_code==200 and claim.call_args.args==("receiving","supervisor","case_one",1)
    with patch("app.api.v1.work_exceptions.WorkExceptionRepository.review",
               return_value={"status":"follow_up_requested","revision":3}) as review:
        result=client.post(path+"/review",headers=auth(),json={
            "expected_revision":2,"decision":"follow_up_requested",
            "review_note":"Contain the shipment pending a physical review.",
        })
    assert result.status_code==200
    assert review.call_args.args[0:5]==("receiving","supervisor","case_one",2,"follow_up_requested")
    bad=[
       {"expected_revision":2,"decision":"release","review_note":"Unsafe shortcut"},
       {"expected_revision":2,"decision":"reviewed","review_note":"ok"},
       {"expected_revision":2,"decision":"reviewed","review_note":"Reviewed case","status":"completed"},
       {"expected_revision":0,"decision":"reviewed","review_note":"Reviewed case"},
    ]
    for payload in bad:
        assert client.post(path+"/review",headers=auth(),json=payload).status_code==422


def test_cases_hide_foreign_scope_and_keep_database_errors_private():
    with patch("app.api.v1.work_exceptions.WorkExceptionRepository.get",side_effect=CaseNotFound()):
        assert client.get("/api/v1/work/exceptions/foreign",headers=auth()).status_code==404
    with patch("app.api.v1.work_exceptions.WorkExceptionRepository.claim",
               side_effect=CaseConflict("Already owned.")):
        assert client.post("/api/v1/work/exceptions/case_one/claim",headers=auth(),
                           json={"expected_revision":1}).status_code==409
    with patch("app.api.v1.work_exceptions.WorkExceptionRepository.get",
               side_effect=RuntimeError("postgresql://private:password@db-server")):
        result=client.get("/api/v1/work/exceptions/case_one",headers=auth())
    assert result.status_code==503 and "db-server" not in result.text

def test_containment_requires_manager_revision_and_forbids_arbitrary_release():
    path="/api/v1/work/exceptions/case_one/action"
    valid={"expected_revision":3,"kind":"containment_recorded",
           "note":"The affected cartons have been segregated from the shipment."}
    assert client.post(path,headers=auth("employee"),json=valid).status_code==403
    for injected in ({"kind":"release"}, {"status":"completed"},
                     {"department_id":"other"}):
        assert client.post(path,headers=auth(),json={**valid,**injected}).status_code==422
    with patch("app.api.v1.work_exceptions.WorkExceptionRepository.action",
               return_value={"revision":4,"status":"follow_up_requested"}) as action:
        result=client.post(path,headers=auth(),json=valid)
    assert result.status_code==200
    assert action.call_args.args==("receiving","supervisor","case_one",3,
                                   "containment_recorded",valid["note"])


def test_linked_handover_requires_owner_and_forbids_forged_identity_fields():
    path="/api/v1/work/exceptions/case_one/handover"
    valid={"recipient_label":"Next-shift supervisor",
           "next_action":"Keep the damaged cartons isolated for QA review.",
           "notes":"Photographs recorded in task checkpoint."}
    for bad in ({"department_id":"other"},{"conversation_id":"forged"},
                {"work_id":"other"},{"status":"completed"}):
        assert client.post(path,headers=auth("employee"),json={**valid,**bad}).status_code==422
    with patch("app.api.v1.work_exceptions.WorkExceptionRepository.handover",
               return_value={"handover_id":"hov_real","status":"submitted"}) as handover:
        result=client.post(path,headers=auth("employee","receiving","operator1"),json=valid)
    assert result.status_code==201
    assert handover.call_args.args==("receiving","operator1","case_one",
                                    valid["recipient_label"],valid["next_action"],valid["notes"])
