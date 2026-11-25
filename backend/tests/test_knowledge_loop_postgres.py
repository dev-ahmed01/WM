"""End-to-end gate for the closed knowledge loop (Scenario D), in a scratch database.

employee asks something with no SOP -> gap + urgent-free support case (once) ->
supervisor reply the employee can read -> admin drafts a proposed SOP -> admin
reviews it -> publishing is refused without manager approval -> manager approves
the exact revision -> admin publishes -> the employee can now find the SOP.
"""
from __future__ import annotations

import hashlib
import importlib.util
import uuid
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import psycopg
import pytest
from fastapi.testclient import TestClient

from app.core import database
from app.core.config import settings
from app.core.security import create_access_token, hash_password

ROOT = Path(__file__).resolve().parents[2]
QUESTION = "How do I recalibrate the thermal ribbon on the pallet labeller?"


def _migrate(dsn: str) -> None:
    spec = importlib.util.spec_from_file_location("migrate_postgres", ROOT / "scripts" / "migrate_postgres.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.migrate(dsn)


@pytest.fixture()
def scratch(monkeypatch):
    base = urlsplit(settings.DATABASE_URL)
    name = "wm_loop_" + uuid.uuid4().hex[:8]
    admin_dsn = urlunsplit(base._replace(path="/postgres"))
    scratch_dsn = urlunsplit(base._replace(path="/" + name))
    with psycopg.connect(admin_dsn, autocommit=True) as conn:
        conn.execute(f'CREATE DATABASE "{name}"')
    database.close_postgres_pool()
    monkeypatch.setattr(settings, "DATABASE_URL", scratch_dsn)
    monkeypatch.setattr(settings, "AUTH_REVALIDATE_DB", False)
    monkeypatch.setattr(settings, "LOCAL_AI_ENABLED", False)
    monkeypatch.setattr(settings, "PUBLISH_REQUIRES_APPROVAL", True)
    _migrate(scratch_dsn)
    try:
        yield scratch_dsn
    finally:
        database.close_postgres_pool()
        with psycopg.connect(admin_dsn, autocommit=True) as conn:
            conn.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')


def _seed(dsn: str) -> dict:
    ids = {"org": "org_loop", "dept": "dept_loop", "admin": "u_admin", "mgr": "u_mgr", "emp": "u_emp"}
    with psycopg.connect(dsn, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute("INSERT INTO security.organizations (id,code,name) VALUES ('org_loop','LOOP','Loop Co')")
        cur.execute("INSERT INTO security.departments (id,code,name,organization_id) VALUES ('dept_loop','LOOP','Ops','org_loop')")
        for uid, role in (("u_admin", "admin"), ("u_mgr", "manager"), ("u_emp", "employee")):
            cur.execute("INSERT INTO security.users (id,email,hashed_password,department_id,full_name) VALUES (%s,%s,%s,'dept_loop',%s)",
                        (uid, f"{uid}@example.test", hash_password("x" * 14), uid))
            cur.execute("INSERT INTO security.user_roles (user_id,role_id) SELECT %s, id FROM security.roles WHERE name=%s", (uid, role))
    return ids


def _publish_existing_sop(dept: str) -> None:
    """One unrelated approved SOP, so the catalogue is not empty (gap flow needs a library)."""
    from app.compiler.pipeline import OWDCompilerPipeline
    from app.services.ingestion import IngestionService
    from demo.sop_catalog import CATALOG
    md = __import__("demo.sop_generator", fromlist=["render"]).render(CATALOG[0]).replace("SOP-INB-001", "SOP-LOOP-001").replace("dm_ops", dept)
    raw = md.encode()
    uri = IngestionService.stage_file(raw, "SOP-LOOP-001.md", "SOP-LOOP-001/v1/" + hashlib.sha256(raw).hexdigest()[:8], department_id=dept)
    report = OWDCompilerPipeline.process_owd(markdown_text=md, title="Supplier arrival", department_id=dept,
                                             user_id="u_admin", stage_file_uri=uri, version_number=1)
    assert report["compilation_status"] == "SUCCESS", report


def _review(c, adm, draft_id) -> int:
    """What an admin does in Procedure Studio: confirm every step against the source, then mark reviewed."""
    draft = c.get(f"/api/v1/procedure/drafts/{draft_id}", headers=adm).json()
    steps = [{"id": st["id"], "instruction": st["instruction"], "source_line": st.get("source_line"),
              "reviewed": True, "output_type": st.get("output_type", "CONFIRMATION"),
              "evidence_type": st.get("evidence_type", "NONE")} for st in draft["steps"]]
    saved = c.put(f"/api/v1/procedure/drafts/{draft_id}", headers=adm,
                  json={"expected_revision": draft["revision"], "title": draft["title"], "steps": steps})
    assert saved.status_code == 200, saved.text
    reviewed = c.post(f"/api/v1/procedure/drafts/{draft_id}/review", headers=adm,
                      json={"expected_revision": saved.json()["revision"]})
    assert reviewed.status_code == 200, reviewed.text
    return reviewed.json()["revision"]


def _h(user: str, role: str) -> dict:
    return {"Authorization": "Bearer " + create_access_token(user, role, "dept_loop")}


@pytest.mark.live_integration
def test_unanswered_question_to_published_sop(scratch):
    from app.main import app

    _seed(scratch)
    _publish_existing_sop("dept_loop")
    emp, adm, mgr = _h("u_emp", "employee"), _h("u_admin", "admin"), _h("u_mgr", "manager")
    with TestClient(app) as c:
        # 1. Employee asks something no SOP covers: honest answer, one support case.
        r = c.post("/api/v1/copilot/message", headers=emp, json={"message": QUESTION}).json()
        assert "won't guess" in r["answer"] and r["requires_escalation"] is True and r["is_grounded"] is False
        # 2. The same question again is counted, not duplicated.
        r2 = c.post("/api/v1/copilot/message", headers=emp, json={"message": QUESTION}).json()
        assert "already has this question" in r2["answer"]
        gaps = c.get("/api/v1/knowledge-gaps", headers=adm).json()["items"]
        assert len(gaps) == 1 and gaps[0]["occurrences"] == 2 and gaps[0]["status"] == "open"
        gap = gaps[0]
        esc = c.get("/api/v1/escalations", headers=adm).json()
        assert len([e for e in esc if "Knowledge gap" in e["reason"]]) == 1

        # 3. A supervisor reply is visible to the employee, marked answered, case closed. Not knowledge.
        assert c.post(f"/api/v1/knowledge-gaps/{gap['id']}/reply", headers=emp, json={"reply": "hack"}).status_code == 403
        rep = c.post(f"/api/v1/knowledge-gaps/{gap['id']}/reply", headers=mgr, json={"reply": "Ask maintenance; we are writing this up."})
        assert rep.status_code == 200 and rep.json()["status"] == "answered"
        mine = c.get("/api/v1/knowledge-gaps/mine", headers=emp).json()["items"]
        assert mine[0]["employee_reply"].startswith("Ask maintenance") and mine[0]["status"] == "answered"
        assert all(e["status"] == "resolved" for e in c.get("/api/v1/escalations", headers=adm).json() if "Knowledge gap" in e["reason"])
        # The reply did not become retrievable guidance.
        again = c.post("/api/v1/copilot/message", headers=emp, json={"message": "recalibrate thermal ribbon pallet labeller"}).json()
        assert "Ask maintenance" not in again["answer"]

        # 4. Admin drafts a proposed SOP from the gap (unpublished), then reviews it.
        assert c.post(f"/api/v1/knowledge-gaps/{gap['id']}/draft", headers=mgr, json={"title": "x" * 6, "steps": ["Do a thing now"]}).status_code == 403
        d = c.post(f"/api/v1/knowledge-gaps/{gap['id']}/draft", headers=adm, json={
            "title": "Recalibrate pallet labeller thermal ribbon",
            "steps": ["Stop the labeller and tell the supervisor before touching it",
                      "Ask the authorised maintenance associate to recalibrate the thermal ribbon",
                      "Print a test label and confirm the barcode scans"]})
        assert d.status_code == 201, d.text
        draft_id = d.json()["draft_id"]
        rev = _review(c, adm, draft_id)

        # 5. Publishing is refused until a manager approves this exact revision.
        pub = {"expected_revision": rev, "approval": "PUBLISH_REVIEWED_SOP"}
        blocked = c.post(f"/api/v1/procedure/drafts/{draft_id}/publish", headers=adm, json=pub)
        assert blocked.status_code == 409 and "manager must approve" in blocked.text
        assert c.post(f"/api/v1/procedure/approvals/{draft_id}", headers=adm,
                      json={"expected_revision": rev, "decision": "approve"}).status_code == 403   # admin cannot approve
        pending = c.get("/api/v1/procedure/approvals", headers=mgr).json()["items"]
        assert [p["id"] for p in pending] == [draft_id] and pending[0]["gap_question"].startswith("How do I recalibrate")
        assert c.post(f"/api/v1/procedure/approvals/{draft_id}", headers=mgr,
                      json={"expected_revision": rev + 5, "decision": "approve"}).status_code == 409  # stale revision
        ok = c.post(f"/api/v1/procedure/approvals/{draft_id}", headers=mgr, json={"expected_revision": rev, "decision": "approve"})
        assert ok.status_code == 200 and ok.json()["approved"] is True

        # 6. Admin publishes; the gap closes; the employee now finds the SOP.
        done = c.post(f"/api/v1/procedure/drafts/{draft_id}/publish", headers=adm, json=pub)
        assert done.status_code == 200, done.text
        assert c.get("/api/v1/knowledge-gaps?status=resolved", headers=adm).json()["items"][0]["id"] == gap["id"]
        found = c.post("/api/v1/copilot/message", headers=emp, json={"message": "recalibrate pallet labeller thermal ribbon"}).json()
        text = (found["answer"] + (found.get("sop_details") or "") + str(found.get("sop_suggestions"))).lower()
        assert "recalibrate" in text or "labeller" in text, found
        assert "won't guess" not in found["answer"]


@pytest.mark.live_integration
def test_manager_can_return_a_draft_and_edit_voids_approval(scratch):
    from app.main import app

    _seed(scratch)
    _publish_existing_sop("dept_loop")
    adm, mgr = _h("u_admin", "admin"), _h("u_mgr", "manager")
    with TestClient(app) as c:
        c.post("/api/v1/copilot/message", headers=_h("u_emp", "employee"), json={"message": QUESTION})
        gap = c.get("/api/v1/knowledge-gaps", headers=adm).json()["items"][0]
        draft_id = c.post(f"/api/v1/knowledge-gaps/{gap['id']}/draft", headers=adm, json={
            "title": "Recalibrate pallet labeller ribbon",
            "steps": ["Stop the labeller and tell the supervisor before touching it",
                      "Ask the authorised maintenance associate to recalibrate it"]}).json()["draft_id"]
        rev = _review(c, adm, draft_id)
        short = c.post(f"/api/v1/procedure/approvals/{draft_id}", headers=mgr, json={"expected_revision": rev, "decision": "return", "note": "no"})
        assert short.status_code == 422
        back = c.post(f"/api/v1/procedure/approvals/{draft_id}", headers=mgr,
                      json={"expected_revision": rev, "decision": "return", "note": "Step 2 must name who is authorised."})
        assert back.status_code == 200 and back.json()["status"] == "draft"
        # Returned drafts cannot be published, and no longer wait in the approval queue.
        assert c.get("/api/v1/procedure/approvals", headers=mgr).json()["items"] == []
        blocked = c.post(f"/api/v1/procedure/drafts/{draft_id}/publish", headers=adm,
                         json={"expected_revision": back.json()["revision"], "approval": "PUBLISH_REVIEWED_SOP"})
        assert blocked.status_code == 409
