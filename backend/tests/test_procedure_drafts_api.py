"""Phase 3 admin access, source import, optimistic draft editing, review denial."""
from types import SimpleNamespace
from unittest.mock import patch
from fastapi.testclient import TestClient
from app.core.security import create_access_token
from app.main import app

client=TestClient(app)

def auth(role="admin",dept="receiving",actor="person1"):
    return {"Authorization":"Bearer "+create_access_token(actor,role,dept)}

def test_only_admin_can_import_and_list_drafts():
    assert client.get("/api/v1/procedure/drafts").status_code==401
    assert client.get("/api/v1/procedure/drafts",headers=auth("employee")).status_code==403
    assert client.post("/api/v1/procedure/drafts/import",headers=auth("employee"),
                       data={"title":"Receiving inspection"},
                       files={"file":("inbound.txt",b"1. Inspect goods on arrival.","text/plain")}).status_code==403
    with patch("app.api.v1.procedure_drafts.ProcedureDraftRepository.list",return_value=[]) as listing:
        res=client.get("/api/v1/procedure/drafts",headers=auth())
    assert res.status_code==200 and res.json()["items"]==[]
    assert listing.call_args.args==("receiving",)


def test_admin_import_creates_review_only_source_and_no_publication():
    with patch("app.api.v1.procedure_drafts.ProcedureDraftRepository.create",
               return_value={"id":"drft_one","status":"draft","revision":1,
                             "steps":[{"reviewed":False}]}) as repo:
        res=client.post("/api/v1/procedure/drafts/import",headers=auth(),
                        data={"title":"Inbound receiving checklist"},
                        files={"file":("inbound.txt",b"1. Inspect the vehicle seal.\n2. Record any carton damage.","text/plain")})
    assert res.status_code==201
    assert res.json()["status"]=="draft"
    assert repo.call_args.args[:2]==("receiving","person1")
    assert repo.call_args.args[2].content.startswith("1. Inspect")
    assert b"carton damage" in repo.call_args.args[3]


def test_review_must_not_accept_forged_department_or_published_status():
    payload={"expected_revision":2,"title":"Warehouse receiving safety",
             "steps":[{"id":"step_111","instruction":"Check the current vehicle seal",
                       "source_line":3,"reviewed":True}]}
    for extra in ({"department_id":"other"},{"status":"published"},
                  {"created_by":"admin_other"}):
        res=client.put("/api/v1/procedure/drafts/drft_1",
                       headers=auth(),json={**payload,**extra})
        assert res.status_code==422
    with patch("app.api.v1.procedure_drafts.ProcedureDraftRepository.update",
               return_value={"id":"drft_1","status":"draft","revision":3}) as changed:
        res=client.put("/api/v1/procedure/drafts/drft_1",headers=auth(),json=payload)
    assert res.status_code==200 and changed.call_args.args[:3]==("receiving","person1","drft_1")
    with patch("app.api.v1.procedure_drafts.ProcedureDraftRepository.review",
               return_value={"status":"reviewed","revision":4}) as reviewed:
        res=client.post("/api/v1/procedure/drafts/drft_1/review",
                        headers=auth(),json={"expected_revision":3})
    assert res.status_code==200 and reviewed.call_args.args==("receiving","person1","drft_1",3)


def test_foreign_drafts_are_hidden_and_store_errors_redacted():
    from app.repositories.procedure_draft_repository import DraftNotFound,DraftConflict
    with patch("app.api.v1.procedure_drafts.ProcedureDraftRepository.get",side_effect=DraftNotFound()):
        assert client.get("/api/v1/procedure/drafts/foreign",headers=auth()).status_code==404
    with patch("app.api.v1.procedure_drafts.ProcedureDraftRepository.review",
               side_effect=DraftConflict("Review the remaining steps.")):
        res=client.post("/api/v1/procedure/drafts/drft_1/review",headers=auth(),
                        json={"expected_revision":1})
    assert res.status_code==409
    with patch("app.api.v1.procedure_drafts.ProcedureDraftRepository.get",
               side_effect=RuntimeError("postgres://private:password@local-db")):
        res=client.get("/api/v1/procedure/drafts/drft_1",headers=auth())
    assert res.status_code==503 and "local-db" not in res.text

def test_original_source_only_downloadable_by_admin_scope():
    assert client.get("/api/v1/procedure/drafts/drft_1/source",
                      headers=auth("employee")).status_code==403
    with patch("app.api.v1.procedure_drafts.ProcedureDraftRepository.source",
               return_value=("validated.txt",b"Original inspection record")) as source:
        res=client.get("/api/v1/procedure/drafts/drft_1/source",
                       headers=auth())
    assert res.status_code==200
    assert res.content==b"Original inspection record"
    assert "attachment;" in res.headers["content-disposition"]
    assert res.headers["cache-control"]=="private, no-store"
    assert source.call_args.args==("receiving","drft_1")
