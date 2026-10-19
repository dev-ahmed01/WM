"""Visual builder contract: existing compiler and explicit protected publish APIs."""
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.core.security import create_access_token
from app.services.procedure_plan import ProcedurePlanError,compile_preview,render_owd
from app.compiler.parser import OWDParser
from app.compiler.validator import OWDValidator

client=TestClient(app)


def auth(role="admin",dept="dept_a"):
    return {"Authorization":"Bearer "+create_access_token("user1",role,dept)}


def sample():
    return {
      "id":"drft_abc123efed65432101234567",
      "department_id":"dept_a","created_by":"user1",
      "title":"Approved goods receiving plan",
      "status":"reviewed","published_version_id":None,"revision":3,
      "steps":[
        {"id":"step_good_one","source_line":3,"reviewed":True,
         "instruction":"Inspect the incoming shipment seal before opening the trailer.",
         "output_type":"CONFIRMATION","evidence_type":"NONE"},
        {"id":"step_good_two","source_line":4,"reviewed":True,
         "instruction":"Record carton condition and attach photographic proof.",
         "output_type":"TEXT_INPUT","evidence_type":"PHOTO_JPEG"},
      ],
      "decision":{"question":"What result was observed after the final checkpoint?",
                  "options":[{"code":"OPT_ACCEPT","label":"Expected condition"},
                             {"code":"OPT_ISSUE","label":"Damage documented"}]},
    }


def test_generated_owd_uses_canonical_validated_engine_and_one_proof_per_step():
    draft=sample()
    md=render_owd(draft)
    assert ":::evidence[PROOF_02]" in md
    parsed=OWDParser.parse(md,title=draft["title"],department_id=draft["department_id"])
    report=OWDValidator.validate(parsed)
    assert report.is_valid,report.errors
    assert sum(len(s.steps) for s in parsed.workflow.states)==2
    assert sum(len(s.evidence_specs) for s in parsed.workflow.states)==1
    assert sum(len(s.decisions) for s in parsed.workflow.states)==1
    assert len(parsed.workflow.states)==5
    assert len(parsed.workflow.states[2].decisions[0].options)==2
    check=compile_preview(draft)
    assert check["valid"] is True,check["validation_errors"]
    assert (check["steps"],check["decisions"],check["states"])==(2,1,5)


def test_linear_plan_compiles_without_a_fabricated_decision():
    draft=sample()
    draft["decision"]={"question":"","options":[]}
    md=render_owd(draft)
    assert ":::decision" not in md
    assert compile_preview(draft)["valid"]


@pytest.mark.parametrize("mutation",[
    lambda d: d["steps"][0].update(reviewed=False),
    lambda d: d["steps"][1].update(evidence_type="SCRIPT"),
    lambda d: d["steps"][0].update(output_type="DOCUMENT_UPLOAD"),
    lambda d: d["decision"]["options"][1].update(code="OPT_ACCEPT"),
    lambda d: d["decision"].update(question=""),
])
def test_unreviewed_or_unsafe_generated_workflow_fails_before_publication(mutation):
    draft=sample()
    mutation(draft)
    with pytest.raises(ProcedurePlanError):
        render_owd(draft)


def test_publish_route_is_admin_only_and_requires_literal_approval():
    url="/api/v1/procedure/drafts/drft_1/publish"
    assert client.post(url,headers=auth("employee"),
                       json={"expected_revision":3,"approval":"PUBLISH_REVIEWED_SOP"}).status_code==403
    assert client.post(url,headers=auth(),
                       json={"expected_revision":3,"approval":"yes"}).status_code==422
    with patch("app.api.v1.procedure_drafts.ProcedurePublisher.publish",
               return_value={"status":"published","version_id":"v1"}) as save:
        result=client.post(url,headers=auth(),
                           json={"expected_revision":3,"approval":"PUBLISH_REVIEWED_SOP"})
    assert result.status_code==200
    assert save.call_args.args==("dept_a","user1","drft_1",3,"PUBLISH_REVIEWED_SOP")


def test_preview_route_only_shows_admin_scoped_workflow():
    url="/api/v1/procedure/drafts/drft_1/compile-preview"
    assert client.get(url,headers=auth("employee")).status_code==403
    with patch("app.api.v1.procedure_drafts.ProcedurePublisher.preview",
               return_value={"valid":True,"can_publish":True}) as source:
        result=client.get(url,headers=auth())
    assert result.status_code==200
    assert source.call_args.args==("dept_a","drft_1")
