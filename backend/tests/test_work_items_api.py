"""Work items cannot be spoofed across departments or mutate published SOPs."""
from unittest.mock import patch
from fastapi.testclient import TestClient
from app.core.security import create_access_token
from app.main import app

client = TestClient(app)


def auth(role="employee", department="receiving", actor="person1"):
    return {"Authorization":"Bearer "+create_access_token(actor,role,department)}


ITEM = {"title":"Inspect incoming goods for damage","work_type":"receiving",
        "priority":"high","assigned_to":"person2","instructions":"Check published receiving SOP."}


def test_manager_can_queue_but_employee_cannot():
    assert client.post("/api/v1/work/items",json=ITEM).status_code == 401
    assert client.post("/api/v1/work/items",headers=auth(),json=ITEM).status_code == 403
    with patch("app.api.v1.work_items.WorkItemRepository.create",
               return_value={"id":"wrk_one","status":"queued"}) as created:
        r=client.post("/api/v1/work/items",headers=auth("manager"),json=ITEM)
    assert r.status_code == 201 and r.json()["status"] == "queued"
    assert created.call_args.args[:2] == ("receiving","person1")
    assert created.call_args.args[-1] == "person2"


def test_schema_rejects_client_authority_and_invalid_status():
    for tamper in ({"department_id":"other"},{"status":"completed"},
                   {"approved":True},{"priority":"critical"}):
        assert client.post("/api/v1/work/items",headers=auth("manager"),
                           json={**ITEM,**tamper}).status_code == 422


def test_employee_scope_and_detail_are_server_derived():
    with patch("app.api.v1.work_items.WorkItemRepository.list",return_value=[]) as listing:
        result=client.get("/api/v1/work/items?department_id=other",headers=auth())
    assert result.status_code == 200
    assert listing.call_args.args == ("receiving","person1",False,100)
    with patch("app.api.v1.work_items.WorkItemRepository.list",return_value=[] ) as listing:
        result=client.get("/api/v1/work/items?limit=15",headers=auth("manager"))
    assert result.status_code == 200
    assert listing.call_args.args == ("receiving","person1",True,15)
    with patch("app.api.v1.work_items.WorkItemRepository.get",return_value=None) as detail:
        missing=client.get("/api/v1/work/items/wrk_secret",headers=auth())
    assert missing.status_code == 404
    assert detail.call_args.args == ("receiving","person1",False,"wrk_secret")


def test_invalid_assignee_is_not_created_and_errors_hide_credentials():
    with patch("app.api.v1.work_items.WorkItemRepository.create",return_value=None):
        denied=client.post("/api/v1/work/items",headers=auth("manager"),json=ITEM)
    assert denied.status_code == 422
    with patch("app.api.v1.work_items.WorkItemRepository.create",
               side_effect=RuntimeError("postgresql://private:password@local-db")):
        failed=client.post("/api/v1/work/items",headers=auth("manager"),json=ITEM)
    assert failed.status_code == 503
    assert "local-db" not in failed.text


def test_reassignment_requires_manager_and_live_in_department():
    assert client.post("/api/v1/work/items/wrk_1/assign",headers=auth(),
                       json={"assigned_to":"person2"}).status_code==403
    with patch("app.api.v1.work_items.WorkItemRepository.assign",
               return_value={"id":"wrk_1","assigned_to":"person2"}) as assign:
        result=client.post("/api/v1/work/items/wrk_1/assign",
                           headers=auth("manager"),json={"assigned_to":"person2"})
    assert result.status_code==200
    assert assign.call_args.args==("receiving","person1","wrk_1","person2")
    assert client.post("/api/v1/work/items/wrk_1/assign",headers=auth("manager"),
                       json={"assigned_to":"person2","department_id":"other"}).status_code==422
    with patch("app.api.v1.work_items.WorkItemRepository.assign",return_value=None):
        denied=client.post("/api/v1/work/items/wrk_1/assign",
                           headers=auth("manager"),json={"assigned_to":"unknown"})
    assert denied.status_code==409
