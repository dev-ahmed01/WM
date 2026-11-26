"""End-to-end acceptance scenarios A-J (English-only build) on a scratch PostgreSQL database.

Each test drives the real FastAPI stack with real tokens and a real database; nothing in the
assistant, workflow, approval or exception layers is mocked except where a failure is the point
(scenario H). Scenario B (Hindi voice) was removed from scope with the English-only decision.
Scenario D lives in test_knowledge_loop_postgres.py.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from scenarios_support import (Api, DEPT_A, DEPT_B, headers, publish_demo_library, publish_org_b_sop,
                               seed_world)
from test_knowledge_loop_postgres import scratch  # noqa: F401  (fixture)


@pytest.fixture(params=["owner", "restricted_runtime"])
def world(request, scratch, monkeypatch):  # noqa: F811
    """The whole acceptance world, run twice: as the database owner (RLS bypassed) and as the restricted
    non-owner runtime login production uses (RLS enforced, POSTGRES_RLS_REFERENCES on)."""
    from app.core import database
    from app.core.config import settings
    from app.main import app
    from scenarios_support import drop_runtime_role, provision_runtime_role
    seed_world(scratch)
    publish_demo_library(DEPT_A)
    publish_org_b_sop(DEPT_B)
    role = None
    if request.param == "restricted_runtime":
        runtime_dsn, role = provision_runtime_role(scratch)
        database.close_postgres_pool()
        monkeypatch.setattr(settings, "DATABASE_URL", runtime_dsn)
        monkeypatch.setattr(settings, "POSTGRES_RLS_REFERENCES", True)
    try:
        with TestClient(app) as client:
            yield Api(client)
    finally:
        database.close_postgres_pool()
        if role:
            monkeypatch.undo()
            drop_runtime_role(scratch, role)


def _finish_workflow(api: Api, user: str, conversation_id: str, limit: int = 12) -> dict:
    """Drive an active workflow to the end with explicit attestations; choose the 'normal' outcome."""
    last: dict = {}
    for _ in range(limit):
        last = api.ask(user, "done", conversation_id)
        if last.get("active_session_status") == "completed" or "Workflow completed" in last["answer"]:
            return last
        if last.get("active_decision_options"):
            option = next(o["option_code"] for o in last["active_decision_options"] if o["option_code"].endswith("NORMAL"))
            adv = api.post(user, f"/copilot/session/{last['active_session_id']}/advance",
                           {"decision_option": option, "rule_results": {}, "values": {}, "use_fallback": False})
            assert adv.status_code == 200, adv.text
            if adv.json()["status"] == "completed":
                return adv.json()
    raise AssertionError(f"workflow did not finish: {last}")


@pytest.mark.live_integration
def test_A_employee_guidance_cited_answer_and_permitted_steps(world):
    api = world
    offer = api.ask("emp1", "How do I receive this shipment?")
    assert "Start it?" in offer["answer"] and "Goods receipt posting" in (offer["sop_details"] or "")
    assert offer["active_session_id"] is None            # nothing starts without confirmation
    conv = offer["conversation_id"]
    started = api.ask("emp1", "yes", conv)
    assert started["active_session_id"] and started["active_step_number"] == 1
    # A question about the current step is answered from the SOP itself, with a citation.
    why = api.ask("emp1", "what if the WMS rejects the receipt?", conv)
    assert "WMS" in why["answer"] and why["citations"] and not why["requires_escalation"]
    # Skipping ahead is refused; steps advance only by explicit attestation.
    skip = api.ask("emp1", "go to step 4", conv)
    assert "will not silently skip" in skip["answer"].lower()
    final = _finish_workflow(api, "emp1", conv)
    assert final.get("active_session_status", final.get("status")) == "completed", final


@pytest.mark.live_integration
def test_C_hinglish_discrepancy_creates_an_authorised_exception(world, monkeypatch):
    api = world
    r1 = api.ask("emp1", "Sir, shipment mein do boxes missing hain")
    conv = r1["conversation_id"]
    assert "2 boxes" in r1["answer"] and "Reply yes" in r1["answer"]
    assert api.get("mgr", "/handover").json()["items"] == []           # proposal alone writes nothing
    r2 = api.ask("emp1", "yes", conv)
    assert "Reported to your shift supervisor" in r2["answer"] and "Stock was not adjusted" in r2["answer"]
    items = api.get("mgr", "/handover").json()["items"]
    assert len(items) == 1
    h = items[0]
    assert (h["exception_type"], h["status"], h["created_by"], h["recipient_label"]) == ("quantity_mismatch", "submitted", "emp1", "Shift supervisor")
    assert "do boxes missing" in h["notes"] and "2 boxes" in h["next_action"]
    # Replaying "yes" must not create a second record.
    api.ask("emp1", "yes", conv)
    assert len(api.get("mgr", "/handover").json()["items"]) == 1
    # The manager can act on it; the employee cannot read other people's handovers.
    hid = items[0]["id"]
    claimed = api.post("mgr", f"/handover/{hid}/claim")
    assert claimed.status_code == 200, claimed.text
    assert api.get("mgr", "/handover").json()["items"][0]["assigned_to_user_id"] == "mgr"
    assert api.get("emp2", "/handover").json()["items"] == []        # other employees see nothing

    # Missing quantity: the assistant asks instead of guessing.
    q1 = api.ask("emp2", "the shipment is short")
    assert "How many" in q1["answer"]
    q2 = api.ask("emp2", "teen", q1["conversation_id"])
    assert "3 boxes" in q2["answer"]
    cancelled = api.ask("emp2", "no", q1["conversation_id"])
    assert "won't send" in cancelled["answer"].lower() and len(api.get("mgr", "/handover").json()["items"]) == 1


@pytest.mark.live_integration
def test_C_failure_to_save_is_reported_honestly(world, monkeypatch):
    from app.repositories.handover_repository import HandoverRepository
    api = world
    r = api.ask("emp1", "2 cartons damaged in the delivery")
    assert "damaged goods" in r["answer"]
    monkeypatch.setattr(HandoverRepository, "submit", staticmethod(lambda *a, **k: (_ for _ in ()).throw(RuntimeError("db down"))))
    out = api.ask("emp1", "yes", r["conversation_id"])
    assert "could not save" in out["answer"].lower() and "nothing was sent" in out["answer"].lower()
    assert "Reported to" not in out["answer"]
    monkeypatch.undo()
    assert api.get("mgr", "/handover").json()["items"] == []


@pytest.mark.live_integration
def test_G_cross_organization_access_is_denied_without_leaking(world):
    api = world
    # Company A's employee asks for Company B's procedure by its distinctive name.
    r = api.ask("emp1", "quarantine of purple widgets")
    blob = (r["answer"] + str(r.get("sop_details")) + str(r.get("sop_suggestions")) + str(r.get("citations"))).lower()
    assert "purple" not in blob.replace("quarantine of purple widgets", "") or "won't guess" in r["answer"]
    assert "purple widgets" not in (r.get("sop_details") or "").lower()
    # Company B's employee does find it.
    own = api.ask("emp_b", "quarantine of purple widgets")
    assert "Quarantine of purple widgets" in (own["sop_details"] or "")
    # Admin A cannot see, read or change B's knowledge, employees or cases.
    b_item = api.get("admin_b", "/knowledge").json()["items"][0]["item"]["id"]
    for method, path in (("get", f"/knowledge/{b_item}"), ("get", f"/knowledge/{b_item}/versions")):
        assert getattr(api, method)("admin1", path).status_code == 404
    assert api.c.delete(f"/api/v1/knowledge/{b_item}", headers=headers("admin1")).status_code == 404
    assert {e["id"] for e in api.get("admin1", "/admin/employees").json()}.isdisjoint({"emp_b", "admin_b"})
    assert api.post("admin1", "/admin/employees/emp_b/recovery-token").status_code == 404
    # An employee has no administrative reach at all.
    for path in ("/admin/employees", "/knowledge", "/knowledge-gaps", "/procedure/drafts", "/escalations"):
        assert api.get("emp1", path).status_code == 403, path
    # Gaps and escalations raised by B never appear for A.
    api.ask("emp_b", "what is the weather on mars")
    assert all("mars" not in g["question"] for g in api.get("admin1", "/knowledge-gaps").json()["items"])
    assert len(api.get("admin_b", "/knowledge-gaps").json()["items"]) == 1


@pytest.mark.live_integration
def test_J_safety_critical_report_stops_work_and_never_invents_repairs(world):
    api = world
    r = api.ask("emp1", "hydraulic leak on the forklift, how do I fix it myself?")
    text = r["answer"].lower()
    assert "stop work" in text and "do not repair" in text and "emergency" in text
    assert r["requires_escalation"] is True
    for forbidden in ("tighten", "replace the", "unscrew", "open the panel", "top up", "restart the"):
        assert forbidden not in text
    case = [e for e in api.get("mgr", "/escalations").json() if "safety" in e["reason"].lower()]
    assert len(case) == 1
    # The same report is stopped even when a workflow is in progress.
    conv = api.ask("emp2", "how do I do goods receipt posting")["conversation_id"]
    api.ask("emp2", "yes", conv)
    mid = api.ask("emp2", "there is smoke coming from the dock", conv)
    assert "stop work" in mid["answer"].lower() and mid["requires_escalation"]


def _photo_b64() -> str:
    import base64, io, os
    from PIL import Image
    buf = io.BytesIO()
    # Noise compresses poorly, so the JPEG clears the SOP's published minimum evidence size.
    Image.frombytes("RGB", (64, 64), os.urandom(64 * 64 * 3)).save(buf, format="JPEG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


@pytest.mark.live_integration
def test_F_manager_intervention_to_closure_and_employee_updates(world):
    api = world
    procs = {p["workflow_code"]: p["workflow_version_id"] for p in api.get("mgr", "/work/execution/procedures").json()["items"]}
    receipt, corrective_sop = procs["SOP_INB_006"], procs["SOP_INB_008"]   # a non-safety SOP whose photo step needs evidence

    wid = api.post("mgr", "/work/items", {"title": "Receive trailer 42", "work_type": "receiving", "priority": "high",
                                          "assigned_to": "emp1"}).json()["id"]
    assert api.post("mgr", f"/work/execution/{wid}/bind", {"workflow_version_id": receipt}).status_code == 200
    assert api.post("emp1", f"/work/execution/{wid}/start").status_code == 200
    blocked = api.post("emp1", f"/work/execution/{wid}/block", {"reason": "Seal number does not match the paperwork."}).json()
    case_id = blocked["case_id"]

    def case() -> dict:
        return api.get("mgr", f"/work/exceptions/{case_id}").json()

    def mine() -> dict:
        items = api.get("emp1", "/work/exceptions/mine").json()["items"]
        assert [i["id"] for i in items] == [case_id]
        return items[0]

    # The employee sees their report immediately, with plain progress and no internal fields.
    first = mine()
    assert first["status"] == "open" and "Waiting for a supervisor" in first["progress"]
    assert "review_note" not in first and "reviewer_id" not in first
    assert api.get("emp2", "/work/exceptions/mine").json()["items"] == []     # others never see it
    assert api.get("emp1", f"/work/exceptions/{case_id}").status_code == 403    # no raw case access

    # Manager: claim -> review -> containment -> remediation plan.
    assert api.post("mgr", f"/work/exceptions/{case_id}/claim", {"expected_revision": case()["revision"]}).status_code == 200
    assert "taken this case" in mine()["progress"]
    for step in (("review", {"decision": "reviewed", "review_note": "Seal mismatch confirmed against the delivery note."}),
                 ("action", {"kind": "containment_recorded", "note": "Trailer held at dock 3 and the driver asked to wait."}),
                 ("action", {"kind": "remediation_proposed", "note": "Recheck cartons with the damaged-goods SOP and photograph them."})):
        r = api.post("mgr", f"/work/exceptions/{case_id}/{step[0]}", {"expected_revision": case()["revision"], **step[1]})
        assert r.status_code == 200, (step[0], r.text)

    # Corrective work is requested by the manager, approved by an admin (never the same person), done by another employee.
    req = api.post("mgr", f"/work/exceptions/{case_id}/corrective", {
        "expected_revision": case()["revision"], "workflow_version_id": corrective_sop, "assigned_to": "emp2",
        "plan_note": "Recheck every carton on the trailer and attach a fresh photograph."})
    assert req.status_code == 201, req.text
    assert "waiting for approval" in mine()["progress"]
    assert api.post("mgr", f"/work/exceptions/{case_id}/corrective/{req.json()['id']}/decision",
                    {"decision": "approved", "decision_note": "Approved: independent recheck is proportionate."}).status_code == 403
    decided = api.post("admin1", f"/work/exceptions/{case_id}/corrective/{req.json()['id']}/decision",
                       {"decision": "approved", "decision_note": "Approved: independent recheck is proportionate."})
    assert decided.status_code == 200, decided.text
    corrective_work = decided.json()["corrective_work_id"]
    assert "approved and assigned" in mine()["progress"]

    # Closure is refused until real corrective evidence exists.
    early = api.post("mgr", f"/work/exceptions/{case_id}/closure/evidence",
                     {"expected_revision": case()["revision"], "review_note": "Trying to close before any corrective work exists."})
    assert early.status_code == 409

    started = api.post("emp2", f"/work/execution/{corrective_work}/start").json()
    guard = 0
    while started.get("status") != "completed" and guard < 12:
        guard += 1
        step = started["step"]
        if started.get("decision_options"):
            started = api.post("emp2", f"/work/execution/{corrective_work}/decision",
                               {"decision_option": started["decision_options"][-1]["option_code"]}).json()
            continue
        files = [{"spec_id": e["id"], "filename": "recheck.jpg", "content_base64": _photo_b64()} for e in step.get("evidence_specs", [])]
        r = api.post("emp2", f"/work/execution/{corrective_work}/step",
                     {"step_id": step["id"], "confirmation": True, "evidence_files": files})
        assert r.status_code == 200, r.text
        started = r.json()
        if started.get("status") == "active" and not started.get("step") and not started.get("decision_options"):
            started = api.post("emp2", f"/work/execution/{corrective_work}/continue").json()
    assert started["status"] == "completed", started

    assert "finished" in mine()["progress"]
    # The reporting employee cannot review their own case; a manager can.
    assert api.post("emp1", f"/work/exceptions/{case_id}/closure/evidence",
                    {"expected_revision": case()["revision"], "review_note": "I would like to approve my own report please."}).status_code == 403
    rev = api.post("mgr", f"/work/exceptions/{case_id}/closure/evidence",
                   {"expected_revision": case()["revision"], "review_note": "Reviewed the completed corrective SOP and the new photograph."})
    assert rev.status_code == 201, rev.text
    assert "independent site check" in mine()["progress"]

    # Final acceptance needs an independent admin: not the approver, not the manager, not the reporter.
    site = {"expected_revision": case()["revision"], "site_record_reference": "QA-SITE-2026-0042",
            "site_acceptance_note": "An independent inspector checked the dock 3 cartons and accepted the corrective photographs.",
            "independent_site_inspection_attested": True}
    assert api.post("admin1", f"/work/exceptions/{case_id}/closure/site", site).status_code == 409   # approved it
    assert api.post("mgr", f"/work/exceptions/{case_id}/closure/site", site).status_code == 403
    closed = api.post("admin2", f"/work/exceptions/{case_id}/closure/site", site)
    assert closed.status_code == 200, closed.text
    assert case()["status"] == "closed"
    final = mine()
    assert final["status"] == "closed" and "Closed" in final["progress"]
    # Replaying the acceptance changes nothing.
    assert api.post("admin2", f"/work/exceptions/{case_id}/closure/site", site).status_code == 409


def _custom_sop_markdown(dept: str, first_step: str) -> bytes:
    """A unique, valid demo SOP ('Pallet wrap audit') whose first step text can be revised."""
    from demo.sop_catalog import S
    from demo.sop_generator import render
    sop = S("SOP-REV-001", "STO", "Pallet wrap audit", "पैलेट रैप ऑडिट", "GEN",
            "Check that outbound pallets are wrapped before staging.",
            [f"{first_step} | First check done",
             "Inspect the wrap for gaps and loose corners | Wrap inspected",
             "Record the pallet as wrapped in the system | Pallet recorded"],
            "A pallet is leaning or the wrap is torn through", "Do not stage it; ask the supervisor to re-wrap",
            "Storage supervisor", False, "pallet=पैलेट; wrap=रैप", "pallet wrap audit stretch film")
    return render(sop).replace("dm_ops", dept).encode()


def _upload_owd(api: Api, user: str, dept: str, first_step: str):
    """Upload an OWD file, then have a manager approve it (the required two-person path). Returns the publish result
    shaped like the old direct upload so callers can read version_number."""
    up = api.c.post("/api/v1/knowledge/upload", headers=headers(user),
                    data={"department_id": dept, "title": "Pallet wrap audit"},
                    files={"file": ("pallet.md", _custom_sop_markdown(dept, first_step), "text/markdown")})
    assert up.status_code == 200 and up.json()["status"] == "pending_approval", up.text
    sub_id = up.json()["version_id"]
    approved = api.post("mgr", f"/procedure/approvals/uploads/{sub_id}", {"decision": "approve"})
    assert approved.status_code == 200, approved.text

    class Result:
        status_code = 200

        @staticmethod
        def json():
            return {"version_number": approved.json()["version_number"]}

        text = approved.text
    return Result


@pytest.mark.live_integration
def test_I_replacing_an_sop_new_questions_use_new_version_active_work_finishes_on_old(world):
    """Versioning policy: a session finishes on the version it STARTED with; every new session gets the
    latest published version. Nothing in flight is silently rewritten or broken."""
    api = world
    v1 = _upload_owd(api, "admin1", DEPT_A, "Check the pallet is on the marked staging bay")
    assert v1.status_code == 200 and v1.json()["version_number"] == 1, v1.text

    conv1 = api.ask("emp1", "how do I do a pallet wrap audit")["conversation_id"]
    started = api.ask("emp1", "yes", conv1)
    assert "marked staging bay" in started["answer"] and started["active_session_id"]
    old_version = started["active_sop_id"]

    v2 = _upload_owd(api, "admin1", DEPT_A, "REVISED: Check the pallet label first, then the marked staging bay")
    assert v2.status_code == 200 and v2.json()["version_number"] == 2, v2.text

    # A new employee gets the new version.
    conv2 = api.ask("emp2", "how do I do a pallet wrap audit")["conversation_id"]
    fresh = api.ask("emp2", "yes", conv2)
    assert "REVISED" in fresh["answer"] and fresh["active_sop_id"] != old_version

    # The in-flight session keeps its original steps and still advances correctly.
    nxt = api.ask("emp1", "done", conv1)
    assert "Inspect the wrap for gaps" in nxt["answer"] and "REVISED" not in nxt["answer"]
    assert nxt["active_sop_id"] == old_version
    # ...and completes on the old version without errors.
    final = _finish_workflow(api, "emp1", conv1)
    assert final.get("active_session_status", final.get("status")) == "completed", final

    # History lists both versions; exactly one is the current published version.
    item = next(i for i in api.get("admin1", "/knowledge").json()["items"] if i["item"]["workflow_code"] == "SOP_REV_001")
    versions = api.get("admin1", f"/knowledge/{item['item']['id']}/versions").json()["versions"]
    assert [v["version_number"] for v in versions] == [2, 1]
    assert [v["status"] for v in versions].count("published") == 1 and versions[0]["status"] == "published"


@pytest.mark.live_integration
def test_E_admin_uploads_a_document_through_review_and_approval_to_employee_retrieval(world):
    from test_knowledge_loop_postgres import _review
    api = world
    doc = (b"Cold room door seal inspection\n\n"
           b"1. Check the cold room door seal for gaps or ice build-up before entering\n"
           b"2. Tell the supervisor if the seal is damaged and do not prop the door open\n"
           b"3. Log the inspection time on the cold room sheet\n")
    question = "how do I inspect the cold room door seal"
    before = api.ask("emp1", question)
    assert "Start it?" not in before["answer"]              # not retrievable before publication

    up = api.c.post("/api/v1/procedure/drafts/import", headers=headers("admin1"),
                    data={"title": "Cold room door seal inspection"}, files={"file": ("cold-room.txt", doc, "text/plain")})
    assert up.status_code == 201, up.text
    draft = up.json()
    assert len(draft["steps"]) == 3 and all(s["reviewed"] is False for s in draft["steps"])   # extracted, not trusted
    assert draft["steps"][0]["source_line"] and "cold room" in draft["source_excerpt"].lower()
    assert api.get("admin1", f"/procedure/drafts/{draft['id']}/source").status_code == 200    # original is downloadable
    assert api.get("emp1", f"/procedure/drafts/{draft['id']}").status_code == 403              # employees never see drafts

    # Unreviewed steps cannot be marked reviewed; the human review is real.
    assert api.post("admin1", f"/procedure/drafts/{draft['id']}/review", {"expected_revision": draft["revision"]}).status_code == 409
    rev = _review(api.c, headers("admin1"), draft["id"])
    pub = {"expected_revision": rev, "approval": "PUBLISH_REVIEWED_SOP"}
    assert api.post("admin1", f"/procedure/drafts/{draft['id']}/publish", pub).status_code == 409   # no approval yet
    assert [p["id"] for p in api.get("mgr", "/procedure/approvals").json()["items"]] == [draft["id"]]
    assert api.post("mgr", f"/procedure/approvals/{draft['id']}", {"expected_revision": rev, "decision": "approve"}).status_code == 200
    done = api.post("admin1", f"/procedure/drafts/{draft['id']}/publish", pub)
    assert done.status_code == 200, done.text

    after = api.ask("emp1", question)
    assert "Start it?" in after["answer"] and "cold room door seal" in (after["sop_details"] or "").lower()
    started = api.ask("emp1", "yes", after["conversation_id"])
    assert "seal" in started["answer"].lower() and started["active_session_id"]
    # Another company's employee cannot retrieve it.
    other = api.ask("emp_b", question)
    assert "Start it?" not in other["answer"] and "cold room" not in (other.get("sop_details") or "").lower()


@pytest.mark.live_integration
def test_H_service_failures_are_reported_honestly_and_lose_nothing(world, monkeypatch):
    from app.core.config import settings
    from app.repositories.conversation_repository import ConversationRepository
    from app.repositories.handover_repository import HandoverRepository
    api = world

    # 1. Ollama configured but unreachable: lookups and step guidance still work, quickly, with no invented text.
    monkeypatch.setattr(settings, "LOCAL_AI_ENABLED", True)
    monkeypatch.setattr(settings, "LOCAL_AI_BASE_URL", "http://127.0.0.1:9")   # nothing listens here
    import time
    t = time.perf_counter()
    offer = api.ask("emp1", "how do I do goods receipt posting")
    assert "Start it?" in offer["answer"]
    started = api.ask("emp1", "yes", offer["conversation_id"])
    assert started["active_session_id"]
    follow = api.ask("emp1", "what if the WMS rejects the receipt?", offer["conversation_id"])
    assert follow["citations"] and "WMS" in follow["answer"]
    novel = api.ask("emp1", "explain the economic theory behind just-in-time inventory", offer["conversation_id"])
    assert novel["requires_escalation"] or "won't guess" in novel["answer"] or "could not find" in novel["answer"].lower()
    assert time.perf_counter() - t < 30, "an unreachable model must not stall the assistant"

    # 2. The database fails while saving a confirmed action: the employee is told, nothing is claimed as done.
    r = api.ask("emp2", "2 cartons damaged in the delivery")
    monkeypatch.setattr(HandoverRepository, "submit", staticmethod(lambda *a, **k: (_ for _ in ()).throw(RuntimeError("connection lost"))))
    failed = api.ask("emp2", "yes", r["conversation_id"])
    assert "could not save" in failed["answer"].lower() and "Reported" not in failed["answer"]
    monkeypatch.undo()
    assert api.get("mgr", "/handover").json()["items"] == []
    # After recovery the employee can retry and the action then really happens, exactly once.
    retry = api.ask("emp2", "2 cartons damaged in the delivery")
    ok = api.ask("emp2", "yes", retry["conversation_id"])
    assert "Reported to your shift supervisor" in ok["answer"]
    assert len(api.get("mgr", "/handover").json()["items"]) == 1

    # 3. Conversation store down: the API says so (503-class), it does not fabricate an answer.
    monkeypatch.setattr(ConversationRepository, "get_or_create_session",
                        staticmethod(lambda *a, **k: (_ for _ in ()).throw(RuntimeError("db unavailable"))))
    from fastapi.testclient import TestClient
    from app.main import app
    with TestClient(app, raise_server_exceptions=False) as quiet:
        resp = quiet.post("/api/v1/copilot/message", headers=headers("emp1"), json={"message": "how do I do goods receipt posting"})
    assert resp.status_code >= 500 and "Start it?" not in resp.text


@pytest.mark.live_integration
def test_B_hindi_voice_is_out_of_scope_and_absent(world):
    """Scenario B was removed with the English-only decision: no voice or translation endpoints exist."""
    for path in ("/copilot/voice", "/copilot/voice/transcribe", "/copilot/voice/speech"):
        assert world.post("emp1", path, {}).status_code == 404, path


@pytest.mark.live_integration
def test_E2_direct_owd_upload_cannot_bypass_manager_approval(world):
    api = world
    md = _custom_sop_markdown(DEPT_A, "Check the pallet is on the marked staging bay")
    files = {"file": ("pallet.md", md, "text/markdown")}
    form = {"department_id": DEPT_A, "title": "Pallet wrap audit"}
    question = "how do I do a pallet wrap audit"

    up = api.c.post("/api/v1/knowledge/upload", headers=headers("admin1"), data=form, files=files)
    assert up.status_code == 200, up.text
    body = up.json()
    assert body["status"] == "pending_approval" and body["deployment_status"] == "PENDING_APPROVAL"
    sub_id = body["version_id"]

    # Nothing is live: no workflow exists and employees cannot retrieve it.
    assert api.get("admin1", "/knowledge").json()["items"] and all(
        i["item"]["workflow_code"] != "SOP_REV_001" for i in api.get("admin1", "/knowledge").json()["items"])
    assert "Start it?" not in api.ask("emp1", question)["answer"]
    # The same bytes cannot be queued twice; the admin sees the pending item; other companies do not.
    assert api.c.post("/api/v1/knowledge/upload", headers=headers("admin1"), data=form, files=files).status_code == 409
    assert [s["id"] for s in api.get("admin1", "/knowledge/submissions?status=pending").json()["items"]] == [sub_id]
    assert api.get("admin_b", "/knowledge/submissions").json()["items"] == []
    assert api.get("emp1", "/knowledge/submissions").status_code == 403

    # Only a manager decides, and the manager sees it in the approvals queue.
    assert api.post("admin1", f"/procedure/approvals/uploads/{sub_id}", {"decision": "approve"}).status_code == 403
    assert api.post("emp1", f"/procedure/approvals/uploads/{sub_id}", {"decision": "approve"}).status_code == 403
    queue = api.get("mgr", "/procedure/approvals").json()
    assert [u["id"] for u in queue["uploads"]] == [sub_id]
    assert "content" not in queue["uploads"][0]                       # the file bytes are never listed

    # Returning needs a real note, publishes nothing, and the file can then be corrected and resubmitted.
    assert api.post("mgr", f"/procedure/approvals/uploads/{sub_id}", {"decision": "return", "note": "no"}).status_code == 422
    back = api.post("mgr", f"/procedure/approvals/uploads/{sub_id}", {"decision": "return", "note": "Step 1 must name the staging bay."})
    assert back.status_code == 200 and back.json()["status"] == "returned"
    assert "Start it?" not in api.ask("emp1", question)["answer"]
    assert api.post("mgr", f"/procedure/approvals/uploads/{sub_id}", {"decision": "approve"}).status_code == 409   # already decided

    fixed = api.c.post("/api/v1/knowledge/upload", headers=headers("admin1"), data=form,
                       files={"file": ("pallet.md", _custom_sop_markdown(DEPT_A, "Check the pallet is on bay 4"), "text/markdown")})
    new_id = fixed.json()["version_id"]
    done = api.post("mgr", f"/procedure/approvals/uploads/{new_id}", {"decision": "approve"})
    assert done.status_code == 200 and done.json()["status"] == "published" and done.json()["version_number"] == 1
    assert api.post("mgr", f"/procedure/approvals/uploads/{new_id}", {"decision": "approve"}).status_code == 409   # replay
    found = api.ask("emp1", question)
    assert "Start it?" in found["answer"] and "Pallet wrap audit" in (found["sop_details"] or "")
    assert api.get("mgr", "/procedure/approvals").json()["uploads"] == []


@pytest.mark.live_integration
def test_unrelated_question_sharing_one_word_does_not_propose_a_wrong_sop(world):
    api = world
    noisy = api.ask("emp1", "how do I check the dock leveller plate")     # no such SOP in the library
    assert "Start it?" not in noisy["answer"] and "won't guess" in noisy["answer"]
    for question, expect in (("I found a damaged box", "Damaged inbound goods"),
                             ("what is the process for requesting leave", "Leave request"),
                             ("how do I do a cycle count", "Cycle counting")):
        good = api.ask("emp1", question)
        assert expect in (good["sop_details"] or "") or expect in good["answer"] or any(
            expect in s["title"] for s in good.get("sop_suggestions", [])), (question, good["answer"])


@pytest.mark.live_integration
def test_G2_analytics_never_cross_company_or_department_boundaries(world):
    """Intelligence Hub endpoints used to return every company's rows when no department was given."""
    api = world
    for user, q in (("emp1", "I found a damaged box"), ("emp2", "how do I do goods receipt posting"),
                    ("emp_b", "quarantine of purple widgets"), ("emp_b", "what is the weather on mars")):
        api.ask(user, q)
    endpoints = ("sop-usage", "faqs", "confusing-procedures", "escalations", "department-adoption", "confidence-trends")
    for who, allowed in (("admin1", {DEPT_A}), ("mgr", {DEPT_A}), ("admin_b", {DEPT_B})):
        for ep in endpoints:
            r = api.get(who, f"/analytics/{ep}")
            assert r.status_code == 200, (who, ep, r.text)
            seen = {row.get("department_id") for row in r.json() if row.get("department_id")}
            assert seen <= allowed, (who, ep, seen)
    # The data really is there for the right company (the guard is not just returning nothing).
    assert any(row["department_id"] == DEPT_B for row in api.get("admin_b", "/analytics/faqs").json())
    assert any(row["department_id"] == DEPT_A for row in api.get("admin1", "/analytics/faqs").json())
    # Asking for another company's department is a 404, for every endpoint and role; employees get 403.
    for who in ("admin1", "mgr"):
        for ep in endpoints[:3] + endpoints[4:]:
            assert api.get(who, f"/analytics/{ep}?department_id={DEPT_B}").status_code == 404, (who, ep)
    assert api.get("emp1", "/analytics/faqs").status_code == 403


@pytest.mark.live_integration
def test_G3_object_ids_from_one_tenant_or_employee_are_useless_to_others(world):
    """Direct-object-reference sweep: ids that belong to emp1 (company A) must not open anything for
    emp2 (same company, different person) or for company B's employee and admin."""
    api = world
    procs = {p["workflow_code"]: p["workflow_version_id"] for p in api.get("mgr", "/work/execution/procedures").json()["items"]}
    offer = api.ask("emp1", "how do I do goods receipt posting")
    conv = offer["conversation_id"]
    started = api.ask("emp1", "yes", conv)
    session_id = started["active_session_id"]
    wid = api.post("mgr", "/work/items", {"title": "Receive trailer 77", "work_type": "receiving", "assigned_to": "emp1"}).json()["id"]
    api.post("mgr", f"/work/execution/{wid}/bind", {"workflow_version_id": procs["SOP_INB_006"]})
    api.post("emp1", f"/work/execution/{wid}/start")
    case_id = api.post("emp1", f"/work/execution/{wid}/block", {"reason": "Seal number does not match the paperwork."}).json()["case_id"]
    handover = api.ask("emp1", "2 cartons damaged in the delivery")
    api.ask("emp1", "yes", handover["conversation_id"])
    hid = api.get("mgr", "/handover").json()["items"][0]["id"]
    api.ask("emp1", "what is the weather on mars")
    gap_id = api.get("admin1", "/knowledge-gaps").json()["items"][0]["id"]
    draft = api.c.post("/api/v1/procedure/drafts/import", headers=headers("admin1"), data={"title": "Seal inspection checklist"},
                       files={"file": ("seal.txt", b"Seal inspection\n\n1. Check the seal number against the paperwork\n2. Tell the supervisor about any mismatch\n", "text/plain")}).json()["id"]

    reads = [f"/copilot/history/{conv}", f"/copilot/session/{session_id}", f"/work/items/{wid}", f"/work/execution/{wid}",
             f"/work/execution/{wid}/timeline", f"/work/exceptions/{case_id}", f"/procedure/drafts/{draft}",
             f"/procedure/drafts/{draft}/source", f"/procedure/drafts/{draft}/compile-preview"]
    writes = [(f"/copilot/session/{session_id}/pause", None), (f"/copilot/session/{session_id}/abandon", {"reason": "not mine to close"}),
              (f"/work/execution/{wid}/start", None), (f"/work/execution/{wid}/pause", None),
              (f"/work/execution/{wid}/block", {"reason": "I should not be able to do this."}),
              (f"/handover/{hid}/claim", None), (f"/knowledge-gaps/{gap_id}/reply", {"reply": "not allowed to reply"}),
              (f"/knowledge-gaps/{gap_id}/dismiss", None), (f"/work/exceptions/{case_id}/claim", {"expected_revision": 1})]
    attackers = ("emp2", "emp_b", "admin_b")
    for who in attackers:
        for path in reads:
            r = api.get(who, path)
            assert r.status_code in (401, 403, 404), (who, "GET", path, r.status_code, r.text[:120])
        for path, body in writes:
            r = api.post(who, path, body)
            assert r.status_code in (401, 403, 404, 409, 422), (who, "POST", path, r.status_code, r.text[:120])
            assert r.status_code != 200, (who, "POST", path)
    # Nothing the attackers tried changed anything.
    assert api.get("emp1", f"/work/execution/{wid}").json()["status"] == "blocked"
    assert api.get("mgr", f"/work/exceptions/{case_id}").json()["status"] == "open"
    assert api.get("admin1", "/knowledge-gaps").json()["items"][0]["status"] == "open"
    # The owner still has access (the guards are not simply denying everything).
    assert api.get("emp1", f"/copilot/history/{conv}").status_code == 200
    assert api.get("emp1", f"/work/execution/{wid}").status_code == 200


@pytest.mark.live_integration
def test_D_gap_draft_is_linked_and_visible_to_the_approver_in_both_database_roles(world):
    """Linking a draft to its gap touches a row-level-security table; it must work as the restricted runtime role."""
    from test_knowledge_loop_postgres import _review
    api = world
    q = "How do I recalibrate the thermal ribbon on the pallet labeller?"
    api.ask("emp1", q)
    gap = api.get("admin1", "/knowledge-gaps").json()["items"][0]
    draft_id = api.post("admin1", f"/knowledge-gaps/{gap['id']}/draft", {
        "title": "Recalibrate pallet labeller ribbon",
        "steps": ["Stop the labeller and tell the supervisor before touching it",
                  "Ask the authorised maintenance associate to recalibrate it"]}).json()["draft_id"]
    rev = _review(api.c, headers("admin1"), draft_id)
    pending = api.get("mgr", "/procedure/approvals").json()["items"]
    assert [p["id"] for p in pending] == [draft_id]
    assert pending[0]["source_gap_id"] == gap["id"], pending[0]
    assert (pending[0]["gap_question"] or "").startswith("How do I recalibrate"), pending[0]
    assert api.post("mgr", f"/procedure/approvals/{draft_id}", {"expected_revision": rev, "decision": "approve"}).status_code == 200
    assert api.post("admin1", f"/procedure/drafts/{draft_id}/publish",
                    {"expected_revision": rev, "approval": "PUBLISH_REVIEWED_SOP"}).status_code == 200
    assert api.get("admin1", "/knowledge-gaps?status=resolved").json()["items"][0]["id"] == gap["id"]


@pytest.mark.live_integration
def test_metrics_summary_counts_only_what_happened_inside_your_scope(world):
    api = world
    c1 = api.ask("emp1", "how do I do goods receipt posting")["conversation_id"]
    api.ask("emp1", "yes", c1)
    api.ask("emp2", "what is the weather on mars")
    api.ask("emp2", "there is smoke coming from the dock")
    api.ask("emp2", "What is the stock level of SKU 12345 in bin A-01?")
    r = api.ask("emp2", "2 cartons damaged in the delivery")
    api.ask("emp2", "yes", r["conversation_id"])
    for _ in range(3):
        api.ask("emp_b", "quarantine of purple widgets")

    a = api.get("admin1", "/analytics/summary?days=30").json()
    m = a["metrics"]
    assert m["active_employees"] == 2                      # emp_b (another company) is not counted
    assert m["knowledge_gaps_raised"] == 1 and m["safety_stops"] == 1 and m["live_data_declined"] == 1
    assert m["actions_confirmed"] == 1 and m["handovers_submitted"] == 1
    assert m["matched_an_approved_sop"] >= 2
    assert m["workflows_started"] == 1 and m["workflows_completed"] == 0 and m["workflow_completion_rate_pct"] == 0.0
    assert m["gap_rate_pct"] == round(100 * 1 / m["questions_received"], 1)
    assert set(a["definitions"]) == set(m), "every reported metric carries its definition"
    assert "response_latency_ms" in a["unavailable"] and "response_latency_ms" not in m   # honest about what is not measured
    b = api.get("admin_b", "/analytics/summary").json()["metrics"]
    assert b["questions_received"] == 3 and b["active_employees"] == 1 and b["knowledge_gaps_raised"] == 0
    assert api.get("mgr", "/analytics/summary").json()["metrics"]["active_employees"] == 2     # manager of the same department
    assert api.get("admin1", f"/analytics/summary?department_id={DEPT_B}").status_code == 404
    assert api.get("emp1", "/analytics/summary").status_code == 403


@pytest.mark.live_integration
def test_roi_estimate_is_labelled_arithmetic_on_supplied_assumptions(world):
    api = world
    body = {"employees": 100, "questions_per_employee_per_week": 5, "minutes_per_supervisor_interruption": 4,
            "share_answered_without_supervisor_pct": 60, "loaded_hourly_cost": 20}
    r = api.post("mgr", "/analytics/roi-estimate", body)
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["kind"] == "ESTIMATE_FROM_ASSUMPTIONS" and "not measured" in out["caveat"]
    assert (out["estimated_questions_per_year"], out["estimated_supervisor_interruptions_avoided"]) == (26000, 15600)
    assert (out["estimated_supervisor_hours_saved"], out["estimated_cost_saved"]) == (1040.0, 20800.0)
    assert out["assumptions"]["employees"] == 100                       # inputs are echoed, never hidden
    assert api.post("admin1", "/analytics/roi-estimate", {**body, "share_answered_without_supervisor_pct": 101}).status_code == 422
    assert api.post("mgr", "/analytics/roi-estimate", {**body, "employees": 0}).status_code == 422
    assert api.post("mgr", "/analytics/roi-estimate", {**body, "surprise": 1}).status_code == 422
    assert api.post("emp1", "/analytics/roi-estimate", body).status_code == 403
