"""True Chromium -> Next.js -> FastAPI -> PostgreSQL browser smoke.

Runs only against disposable CI services and real PostgreSQL state. The Phase 5B
microphone/ASR preview is an isolated browser fixture because the heavy speech
model is disabled in CI; task guidance and workflow authorization stay real.
Tests draft approval, archival, and departmental isolation.
"""
from __future__ import annotations

import io
import json
import hashlib
import hmac
import time
import os
import re
import psycopg
from PIL import Image
import signal
from pathlib import Path

from playwright.sync_api import sync_playwright, expect

BASE = os.environ.get("WORKMATE_BROWSER_URL", "http://127.0.0.1:3000")
PASSWORD = os.environ.get("WORKMATE_E2E_PASSWORD")
DOCUMENT_NAME = "Controlled Receiving Policy"
DOCUMENT_TEXT = (
    "During receiving, inspect the security seal and scan the barcode. "
    "For damaged cartons, quarantine the goods and notify the supervisor "
    "before putaway. This is a reference, not an executable SOP."
)


def seed_published_execution_fixture():
    """Disposable, synthetic published SOP specifically for browser execution tests."""
    dsn = os.environ.get("DATABASE_URL", "")
    assert os.environ.get("WORKMATE_BROWSER_SMOKE") == "1"
    assert "@localhost:" in dsn and os.environ.get("APP_ENV") in ("dev","test","development")
    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("""INSERT INTO knowledge_studio.workflows
                (id,workflow_code,title,department_id,category,created_by)
                VALUES('e2e_workflow','E2E_RECEIVING','Synthetic receiving inspection',
                       'e2e_ops','receiving','e2e_admin')""")
            cur.execute("""INSERT INTO knowledge_studio.workflow_versions
                (id,workflow_id,version_number,stage_file_uri,ast_hash,status,published_at)
                VALUES('e2e_sop_version','e2e_workflow',1,'pgobj:synthetic_fixture',
                       %s,'published',CURRENT_TIMESTAMP)""",("b"*64,))
            for state,kind,name,start,terminal,index in (
                ("e2e_initial","ATOMIC_STEP","Check incoming goods",True,False,1),
                ("e2e_choice","DECISION","Condition assessment",False,False,2),
                ("e2e_done","END","Receiving inspection completed",False,True,3),
            ):
                cur.execute("""INSERT INTO knowledge_studio.workflow_states
                    (id,workflow_version_id,state_key,state_type,title,
                     is_initial,is_terminal,ordinal_index)
                    VALUES(%s,'e2e_sop_version',%s,%s,%s,%s,%s,%s)""",
                    (state,state,kind,name,start,terminal,index))
            for step,kind,title,index in (
                ("e2e_step_seal","CONFIRMATION","Inspect the inbound seal",1),
                ("e2e_step_carton","TEXT_INPUT","Record carton condition and attach a photo",2),
            ):
                cur.execute("""INSERT INTO knowledge_studio.workflow_steps
                    (id,state_id,step_code,instruction,expected_output_type,
                     is_mandatory,ordinal_index)
                    VALUES(%s,'e2e_initial',%s,%s,%s,TRUE,%s)""",
                    (step,step,title,kind,index))
            cur.execute("""INSERT INTO knowledge_studio.workflow_evidence_specs
                (id,step_id,evidence_type,is_required,min_size_bytes)
                VALUES('e2e_photo_spec','e2e_step_carton','PHOTO_JPEG',TRUE,6)""")
            cur.execute("""INSERT INTO knowledge_studio.workflow_transitions
                (id,from_state_id,to_state_id,condition_type)
                VALUES('e2e_tr_init','e2e_initial','e2e_choice','ALWAYS')""")
            cur.execute("""INSERT INTO knowledge_studio.workflow_transitions
                (id,from_state_id,to_state_id,condition_type,condition_expression)
                VALUES('e2e_tr_end','e2e_choice','e2e_done',
                       'DECISION_OPTION','ACCEPT')""")
            cur.execute("""INSERT INTO knowledge_studio.workflow_decision_options
                (id,state_id,option_code,option_label,target_state_id)
                VALUES('e2e_opt_accept','e2e_choice','ACCEPT','Accept and finish','e2e_done')""")
    return "e2e_sop_version"


def sign_in(browser, email):
    page = browser.new_page()
    page.set_default_timeout(12000)
    page.set_default_navigation_timeout(12000)
    page.goto(f"{BASE}/login", wait_until="domcontentloaded")
    expect(page.get_by_role("heading", name="Welcome back")).to_be_visible()
    page.get_by_placeholder("name@workmate.ai").fill(email)
    page.get_by_placeholder("Enter your password").fill(PASSWORD)
    with page.expect_response(lambda resp: "/api/session/login" in resp.url, timeout=15000) as auth:
        page.get_by_role("button", name="Sign in").click()
    login_response = auth.value
    if login_response.status != 200:
        raise AssertionError(f"Login proxy status {login_response.status}: {login_response.text()[:350]}")
    try:
        page.wait_for_url("**/procedure-studio" if "admin" in email else "**/control-room" if "manager" in email else "**/workspace", timeout=12000)
        if "admin" not in email and "manager" not in email:
            expect(page.get_by_role("heading", name="Today's work")).to_be_visible()
            # Guided assistance is accessible from work, but never auto-sends.
            page.get_by_role("link", name="WorkMate Assist").click()
            expect(page.get_by_role("heading", name="Operational Copilot")).to_be_visible()
            expect(page.locator("textarea")).to_be_visible()
    except Exception as exc:
        cookie_names = [(item['name'], item['httpOnly'], item['secure']) for item in page.context.cookies([BASE])]
        profile_status = page.evaluate("async () => (await fetch('/api/session/me')).status")
        raise AssertionError(
            f"Login session not accepted: current={page.url} cookies={cookie_names}, me_status={profile_status}"
        ) from exc
    return page


def search_sources(page, expected: bool):
    page.goto(f"{BASE}/copilot/sources")
    expect(page.get_by_role("heading", name="Find an approved source")).to_be_visible()
    field = page.get_by_role("textbox", name="Search reference documents")
    field.fill("security seal")
    page.get_by_role("button", name="Search", exact=True).click()
    if expected:
        expect(page.get_by_role("heading", name=DOCUMENT_NAME)).to_be_visible(timeout=20000)
        expect(page.get_by_text("quarantine the goods")).to_be_visible()
    else:
        expect(page.get_by_text("No verified matching passages")).to_be_visible(timeout=20000)
        assert page.get_by_role("heading", name=DOCUMENT_NAME).count() == 0


def ask_reference(page, question: str):
    """Actual Chromium composer → Next.js BFF → FastAPI → PostgreSQL."""
    page.goto(f"{BASE}/copilot")
    expect(page.get_by_role("heading", name="Operational Copilot")).to_be_visible()
    page.get_by_role("button", name="Ask documents").click()
    assert page.get_by_role("button", name="Ask documents").get_attribute("aria-pressed") == "true"
    expect(page.get_by_role("button", name="Voice input is available in SOP guidance mode")).to_be_disabled()
    page.locator("textarea").fill(question)
    with page.expect_response(
        lambda response: response.url.endswith("/api/backend/copilot/message")
        and response.request.method == "POST", timeout=30000,
    ) as captured:
        page.get_by_role("button", name="Send message").click()
    response = captured.value
    assert response.status == 200, f"Reference answer status {response.status}: {response.text()[:300]}"
    data = response.json()
    assert data["answer"] and data["conversation_id"]
    expect(page.get_by_role("log").get_by_text(question, exact=True)).to_be_visible(timeout=15000)
    return data


def verify_history_resume(page, conversation_id: str):
    page.goto(f"{BASE}/copilot/history")
    expect(page.get_by_role("heading", name="Session history")).to_be_visible()
    target = page.locator(f'a[href="/copilot?session={conversation_id}"]')
    expect(target).to_be_visible(timeout=15000)
    target.click()
    expect(page.get_by_role("heading", name="Operational Copilot")).to_be_visible()
    expect(page.get_by_role("log").locator("article").first).to_be_visible(timeout=15000)


def main():
    if hasattr(signal, "SIGALRM"):
        def timeout_handler(_signum, _frame):
            raise TimeoutError("Browser smoke exceeded 120 seconds; inspect the active Python stack")
        signal.signal(signal.SIGALRM, timeout_handler)
        signal.alarm(120)
    if os.environ.get("WORKMATE_BROWSER_SMOKE") != "1" or not PASSWORD:
        raise SystemExit("Refusing non-test browser session")
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        admin = None
        employee = None
        outsider = None
        manager = None
        site_admin = None
        try:
            admin = sign_in(browser, "e2e_admin@workmate.test")
            admin.screenshot(path="/tmp/workmate-phase1-procedure-studio.png", full_page=True)
            # Phase 3A: ordinary SOP -> saved, manually checked, reviewed draft.
            admin.goto(f"{BASE}/procedure-studio/drafts")
            expect(admin.get_by_role("heading",name="Build from a document")).to_be_visible()
            admin.get_by_label("Procedure document").set_input_files({
                "name":"receiving-procedure.txt",
                "mimeType":"text/plain",
                "buffer":(
                    "Receiving SOP\\n"
                    "1. Inspect the inbound trailer seals before unloading.\\n"
                    "2. Record visible carton damage for the shift supervisor.\\n"
                ).replace("\\n","\n").encode("utf-8"),
            })
            admin.get_by_label("Procedure title").fill("Inbound goods validation")
            with admin.expect_response(
                lambda response: response.url.endswith("/api/backend/procedure/drafts/import")
                and response.request.method == "POST",timeout=20000
            ) as imported:
                admin.get_by_role("button",name="Create editable procedure draft").click()
            assert imported.value.status==201
            # Next.js navigates immediately after import: read its draft ID from
            # the resulting URL instead of an already-released response body.
            admin.wait_for_url("**/procedure-studio/drafts/drft_*",timeout=15000)
            imported_id=admin.url.rsplit("/",1)[-1]
            expect(admin.get_by_role("heading",name="Procedure editor")).to_be_visible(timeout=15000)
            with admin.expect_download() as original_download:
                admin.get_by_role("link",name="Download original").click()
            assert b"Inspect the inbound trailer seals" in original_download.value.path().read_bytes()
            step_checks=admin.get_by_label("Checked against original source")
            assert step_checks.count()==2
            for checkbox in step_checks.all():
                checkbox.check()
            # Phase 3B: configure an actual conditional outcome branch and
            # a photo-evidence requirement using the visual editor.
            admin.locator('select[id^="output-"]').nth(1).select_option("TEXT_INPUT")
            admin.locator('select[id^="evidence-"]').nth(1).select_option("PHOTO_JPEG")
            admin.get_by_text("Require final outcome selection").click()
            admin.get_by_role("button",name="Save revision").click()
            expect(admin.get_by_text("Changes saved.",exact=False)).to_be_visible(timeout=15000)
            # Changed proof obligations must be acknowledged again before review.
            admin.get_by_role("checkbox").nth(1).check()
            admin.get_by_role("button",name="Save revision").click()
            expect(admin.get_by_text("Changes saved.",exact=False)).to_be_visible(timeout=15000)
            with admin.expect_response(
                lambda response: response.url.endswith("/api/backend/procedure/drafts/"+imported_id+"/review")
                and response.request.method=="POST",timeout=20000
            ) as reviewed:
                admin.get_by_role("button",name="Mark draft reviewed").click()
            assert reviewed.value.status==200
            admin.screenshot(path="/tmp/workmate-phase3-procedure-editor.png",full_page=True)
            admin.get_by_role("button",name="Validate compiled workflow").click()
            expect(admin.get_by_text("Compiler validation passed")).to_be_visible(timeout=15000)
            assert admin.get_by_text("2 worker steps",exact=False).is_visible()
            admin.get_by_text("I confirm this reviewed workflow",exact=False).click()
            with admin.expect_response(
                lambda r: r.url.endswith("/api/backend/procedure/drafts/"+imported_id+"/publish")
                and r.request.method=="POST", timeout=30000
            ) as publication:
                admin.get_by_role("button",name="Publish reviewed workflow").click()
            assert publication.value.status==200,publication.value.text()
            published_version=publication.value.json()["version_id"]
            # Verify both evidence policy and supervisor hard stop survived
            # the actual canonical PostgreSQL compiler/loader.
            with psycopg.connect(os.environ["DATABASE_URL"]) as db:
                with db.cursor() as cur:
                    cur.execute("""
                        SELECT COUNT(*) FROM knowledge_studio.workflow_evidence_specs e
                        JOIN knowledge_studio.workflow_steps st ON st.id=e.step_id
                        JOIN knowledge_studio.workflow_states state ON state.id=st.state_id
                        WHERE state.workflow_version_id=%s
                          AND e.evidence_type='PHOTO_JPEG' AND e.is_required=TRUE
                    """,(published_version,))
                    assert cur.fetchone()[0]==1
                    cur.execute("""
                        SELECT COUNT(*) FROM knowledge_studio.workflow_rules rule
                        JOIN knowledge_studio.workflow_states state ON state.id=rule.state_id
                        WHERE state.workflow_version_id=%s AND state.state_type='ESCALATION'
                          AND rule.enforcement_level='HARD_STOP'
                    """,(published_version,))
                    assert cur.fetchone()[0]==1
            expect(admin.get_by_text("Published version:",exact=False)).to_be_visible(timeout=15000)
            admin.evaluate("window.scrollTo(0,0)")
            admin.screenshot(path="/tmp/workmate-phase3b-published-workflow.png",full_page=True)
            status=admin.request.get(f"{BASE}/api/backend/procedure/drafts/{imported_id}")
            assert status.status==200 and status.json()["status"]=="published"
            # Send JSON from the authenticated same-origin browser, including
            # the usual CSRF protections, to prove replay is a conflict.
            duplicate=admin.evaluate("""async ({id,revision}) => {
                const response=await fetch('/api/backend/procedure/drafts/'+id+'/publish',{
                    method:'POST',headers:{'Content-Type':'application/json'},
                    body:JSON.stringify({expected_revision:revision,approval:'PUBLISH_REVIEWED_SOP'})
                });
                return response.status;
            }""",{"id":imported_id,"revision":reviewed.value.json()["revision"]})
            assert duplicate==409,duplicate


            # Force short-lived access-cookie expiry while retaining the
            # refresh cookie: the server must rotate the refresh chain.
            old_cookies = {c["name"]: c["value"] for c in admin.context.cookies([BASE])}
            assert "wm_refresh" in old_cookies
            admin.context.clear_cookies(name="wm_access")
            assert admin.evaluate("async () => (await fetch('/api/session/me')).status") == 200
            new_cookies = {c["name"]: c["value"] for c in admin.context.cookies([BASE])}
            assert new_cookies.get("wm_access")
            assert new_cookies.get("wm_refresh") != old_cookies["wm_refresh"]
            admin.goto(f"{BASE}/knowledge-studio/upload")
            expect(admin.get_by_role("heading", name="Add knowledge")).to_be_visible()
            admin.locator("#document-preview-upload").set_input_files({
                "name": "controlled-receiving.txt",
                "mimeType": "text/plain",
                "buffer": DOCUMENT_TEXT.encode("utf-8"),
            })
            expect(admin.get_by_role("heading", name="Save for administrator review")).to_be_visible(timeout=30000)
            admin.get_by_role("textbox", name="Document title").fill(DOCUMENT_NAME)
            admin.locator("select").select_option("e2e_ops")
            admin.get_by_role("button", name="Save as draft").click()
            expect(admin.get_by_text("Document saved as a draft")).to_be_visible(timeout=30000)

            employee = sign_in(browser, "e2e_employee@workmate.test")
            employee.goto(f"{BASE}/procedure-studio/drafts")
            employee.wait_for_url("**/workspace",timeout=15000)
            assert employee.request.get(
                f"{BASE}/api/backend/procedure/drafts/{imported_id}"
            ).status==403
            # Capture the actual desk, not the starter draft destination.
            employee.goto(f"{BASE}/workspace")
            expect(employee.get_by_role("heading", name="Today\u0027s work")).to_be_visible()
            employee.evaluate("window.scrollTo(0,0)")
            employee.screenshot(path="/tmp/workmate-eval-operations-desk.png", full_page=True)
            employee.set_viewport_size({"width": 375, "height": 812})
            employee.goto(f"{BASE}/workspace")
            expect(employee.get_by_role("heading", name="Today\u0027s work")).to_be_visible()
            document_width = employee.evaluate("document.documentElement.scrollWidth")
            viewport_width = employee.evaluate("window.innerWidth")
            assert document_width <= viewport_width + 2, f"Mobile overflow: {document_width} > {viewport_width}"
            employee.screenshot(path="/tmp/workmate-eval-mobile-desk.png")
            employee.set_viewport_size({"width": 1280, "height": 720})
            outsider = sign_in(browser, "e2e_other@workmate.test")
            manager = sign_in(browser, "e2e_manager@workmate.test")
            expect(manager.get_by_role("heading", name="Control room")).to_be_visible()
            # Phase 6A: authentic two-person WMS event intake with actual
            # PostgreSQL queue creation only AFTER explicit human review.
            manager.goto(f"{BASE}/work/integrations")
            expect(manager.get_by_role("heading",name="Integration inbox")).to_be_visible()
            manager.get_by_label("Source format").select_option("custom_wms")
            manager.get_by_label("External event ID").fill("shipment.received.7201")
            manager.get_by_label("External work ID").fill("SHIP-7201")
            manager.get_by_label("Work title").fill("Check WMS inbound shipment 7201")
            manager.get_by_label("Work type").select_option("receiving")
            manager.get_by_label("Priority").select_option("high")
            manager.get_by_label("Intended worker").select_option("e2e_employee")
            manager.get_by_label("Source instructions").fill(
                "Match the source shipment with the dock receipt and inspect sealed cartons."
            )
            with manager.expect_response(
                lambda response:response.url.endswith("/api/backend/work/integrations/intake")
                    and response.request.method=="POST",timeout=20000
            ) as intake_staged:
                manager.get_by_role("button",name="Stage for review").click()
            assert intake_staged.value.status==201,intake_staged.value.text()
            intake_id=intake_staged.value.json()["id"]
            assert intake_staged.value.json()["status"]=="pending"
            assert intake_staged.value.json()["work_item_id"] is None
            assert manager.request.post(
                f"{BASE}/api/backend/work/integrations/intake/{intake_id}/decision",
                headers={"Origin":BASE},
                data={"decision":"accepted",
                      "decision_note":"A submitter cannot independently approve this order."}
            ).status==409
            assert employee.request.get(
                f"{BASE}/api/backend/work/integrations/intake"
            ).status==403
            admin.goto(f"{BASE}/work/integrations")
            expect(admin.get_by_role("heading",name="Integration inbox")).to_be_visible()
            admin.get_by_role("button",name=re.compile("Check WMS inbound shipment 7201")).click()
            admin.get_by_label("Independent review note").fill(
                "Receipt verified against inbound dock order; SOP must be bound separately."
            )
            with admin.expect_response(
                lambda response:response.url.endswith(
                    f"/api/backend/work/integrations/intake/{intake_id}/decision")
                    and response.request.method=="POST",timeout=20000
            ) as intake_accepted:
                admin.get_by_role("button",name="Accept into queue").click()
            assert intake_accepted.value.status==200,intake_accepted.value.text()
            imported_work=intake_accepted.value.json()["work_item_id"]
            assert intake_accepted.value.json()["status"]=="accepted"
            imported_state=manager.request.get(
                f"{BASE}/api/backend/work/execution/{imported_work}"
            ).json()
            assert imported_state["status"]=="queued" and imported_state["session_id"] is None
            assert imported_state["workflow_version_id"] is None
            admin.screenshot(path="/tmp/workmate-phase6a-integration-approved.png",full_page=True)
            retry=manager.request.post(
                f"{BASE}/api/backend/work/integrations/intake",
                headers={"Origin":BASE},
                data={
                  "source_system":"custom_wms",
                  "external_event_id":"shipment.received.7201",
                  "external_work_id":"SHIP-7201",
                  "title":"Check WMS inbound shipment 7201",
                  "work_type":"receiving","priority":"high",
                  "instructions":"Match the source shipment with the dock receipt and inspect sealed cartons.",
                  "assigned_to":"e2e_employee"
                },
            )
            assert retry.status==201 and retry.json()["replayed"] is True
            assert retry.json()["work_item_id"]==imported_work
            assert outsider.request.get(f"{BASE}/api/backend/work/items/{imported_work}").status==404

            # Phase 6B: pre-provisioned HMAC secret and unsigned HTTP rejection.
            # Real FastAPI ingress is called without cookies/authorization.
            admin.goto(f"{BASE}/work/integrations")
            admin.get_by_label("Connector signing key ID").fill("e2e_signed_wms")
            admin.get_by_label("Connector source type").select_option("custom_wms")
            with admin.expect_response(
                lambda response:response.url.endswith("/api/backend/work/integrations/sources")
                    and response.request.method=="POST",timeout=20000
            ) as connector_created:
                admin.get_by_role("button",name="Register preconfigured source").click()
            assert connector_created.value.status==201,connector_created.value.text()
            assert connector_created.value.json()["status"]=="active"
            webhook_url="http://127.0.0.1:8000/api/v1/work/integrations/webhooks/e2e_signed_wms"
            signed_order={
                "source_system":"custom_wms",
                "external_event_id":"receipt.signed.8005",
                "external_work_id":"SIGNED-8005",
                "title":"Review signed inbound shipment 8005",
                "work_type":"receiving","priority":"high",
                "instructions":"Record sealed cartons in the warehouse receiving bay.",
                "assigned_to":"e2e_employee",
            }
            raw=json.dumps(signed_order,separators=(",",":")).encode()
            stamp=str(int(time.time()))
            source_secret=b"ci-only-signed-warehouse-secret-has-36-bytes-for-tests"
            def signature(nonce,payload=raw):
                mac=hmac.new(source_secret,b"v1\n"+stamp.encode()+b"\n"+nonce.encode()+b"\n"+payload,
                             hashlib.sha256).hexdigest()
                return {"X-WM-Timestamp":stamp,"X-WM-Nonce":nonce,
                        "X-WM-Signature":"v1="+mac,"Content-Type":"application/json"}
            assert admin.request.post(webhook_url,data=raw).status==401
            wrong=signature("browser_nonce_bad_123456")
            wrong["X-WM-Signature"]="v1="+"0"*64
            assert admin.request.post(webhook_url,data=raw,headers=wrong).status==401
            first=admin.request.post(webhook_url,data=raw,
                                     headers=signature("browser_nonce_first_123456"))
            assert first.status==202,first.text()
            assert first.json()["status"]=="staged"
            signed_intake=first.json()["intake_id"]
            assert admin.request.post(webhook_url,data=raw,
                headers=signature("browser_nonce_first_123456")).status==409
            again=admin.request.post(webhook_url,data=raw,
                                     headers=signature("browser_nonce_retry_123456"))
            assert again.status==202 and again.json()["status"]=="replayed"
            assert again.json()["intake_id"]==signed_intake
            bad_payload=json.dumps({**signed_order,"status":"completed"}).encode()
            invalid=admin.request.post(webhook_url,data=bad_payload,
                                       headers=signature("browser_nonce_invalid_123456",bad_payload))
            assert invalid.status==422
            manager.goto(f"{BASE}/work/integrations")
            manager.get_by_role("button",name=re.compile("Review signed inbound shipment 8005")).click()
            manager.get_by_label("Independent review note").fill(
                "Receipt verified against signed warehouse source order; SOP remains separate."
            )
            with manager.expect_response(
                lambda response:response.url.endswith(
                    "/api/backend/work/integrations/intake/"+signed_intake+"/decision")
                    and response.request.method=="POST",timeout=20000
            ) as signed_approval:
                manager.get_by_role("button",name="Accept into queue").click()
            assert signed_approval.value.status==200,signed_approval.value.text()
            signed_work=signed_approval.value.json()["work_item_id"]
            signed_position=manager.request.get(f"{BASE}/api/backend/work/execution/{signed_work}").json()
            assert signed_position["status"]=="queued" and signed_position["session_id"] is None
            admin.goto(f"{BASE}/work/integrations")
            # Phase 6D: health is real committed Postgres state, never GO.
            expect(admin.get_by_role("heading",name="Integration readiness")).to_be_visible(timeout=15000)
            readiness=admin.request.get(
                f"{BASE}/api/backend/work/integrations/operations/readiness")
            assert readiness.status==200,readiness.text()
            signals=readiness.json()
            assert signals["decision"]=="NO_GO"
            assert signals["counts"]["sources"]==1
            assert signals["counts"]["inbound_24h"]>=3
            assert signals["counts"]["open_alerts"]>=2
            assert {"invalid_inbound","outbound_unconfigured"} <= {
                row["code"] for row in signals["alerts"]}
            assert manager.request.get(
                f"{BASE}/api/backend/work/integrations/operations/readiness").status==403
            assert employee.request.get(
                f"{BASE}/api/backend/work/integrations/operations/readiness").status==403
            admin.get_by_role("button",name=re.compile("Signed incoming deliveries were rejected")).click()
            admin.get_by_label("Operational response").select_option("acknowledged")
            admin.get_by_label("Operator note").fill(
                "Inspected the rejected vendor schema and escalated remediation to the integration owner.")
            with admin.expect_response(
                lambda response:response.url.endswith("/api/backend/work/integrations/operations/actions")
                    and response.request.method=="POST",timeout=20000
            ) as ops_response:
                admin.get_by_role("button",name="Record response").click()
            assert ops_response.value.status==201,ops_response.value.text()
            assert ops_response.value.json()["health_cleared"] is False
            expect(admin.get_by_text("Operator response recorded.",exact=False)).to_be_visible()
            health_after=admin.request.get(
                f"{BASE}/api/backend/work/integrations/operations/readiness").json()
            assert health_after["counts"]["open_alerts"]>=2
            assert health_after["latest_actions"][0]["issue_code"]=="invalid_inbound"
            # Full-page evidence should include the fixed navigation from y=0;
            # auto-scroll from the incident action would otherwise displace it.
            admin.evaluate("window.scrollTo(0,0)")
            admin.screenshot(path="/tmp/workmate-phase6d-operations-readiness.png",full_page=True)
            admin.get_by_role("button",name=re.compile("^e2e_signed_wms")).click()
            expect(admin.get_by_text("3 deliveries",exact=False)).to_be_visible(timeout=15000)
            admin.screenshot(path="/tmp/workmate-phase6b-signed-connector-health.png",full_page=True)
            # Phase 6C: accepted signed work has a single pending outbound
            # event; no connector host/secret is configured in this CI process,
            # so no third-party network call is made.
            outbound=admin.request.get(
                f"{BASE}/api/backend/work/integrations/sources/e2e_signed_wms/outbox"
            )
            assert outbound.status==200,outbound.text()
            outbound_items=outbound.json()["items"]
            assert len(outbound_items)==1,outbound_items
            assert outbound_items[0]["work_item_id"]==signed_work
            assert outbound_items[0]["status"]=="pending"
            assert outbound_items[0]["attempts"]==0
            assert outbound_items[0]["ack_reference"] is None
            assert manager.request.get(
                f"{BASE}/api/backend/work/integrations/sources/e2e_signed_wms/outbox"
            ).status==403
            # Other-department browser persona has employee role: fail at RBAC.
            # Live PG separately verifies a foreign *admin* receives 404.
            assert outsider.request.get(
                f"{BASE}/api/backend/work/integrations/sources/e2e_signed_wms/outbox"
            ).status==403
            expect(admin.get_by_text("Outbound reconciliation")).to_be_visible()
            expect(admin.get_by_text("Awaiting dispatch")).to_be_visible()
            admin.screenshot(path="/tmp/workmate-phase6c-outbound-reconciliation.png",full_page=True)
            admin.get_by_role("button",name="Disable source").click()
            expect(admin.get_by_role("button",name="Enable source")).to_be_visible(timeout=15000)
            assert admin.request.post(webhook_url,data=raw,
                headers=signature("browser_nonce_disabled_123456")).status==401
            assert outsider.request.get(f"{BASE}/api/backend/work/items/{signed_work}").status==404
            manager.goto(f"{BASE}/knowledge-studio")
            manager.wait_for_url("**/control-room", timeout=12000)
            # Phase 1 real manager intake -> PostgreSQL assignment -> employee-only view.
            manager.goto(f"{BASE}/control-room")
            manager.get_by_role("button", name="New assignment").click()
            expect(manager.get_by_role("heading", name="Create assignment")).to_be_visible()
            manager.get_by_label("Task title").fill("Inspect inbound pallet under received goods SOP")
            manager.get_by_label("Work type").select_option("receiving")
            manager.get_by_label("Priority").select_option("high")
            manager.get_by_label("Assign employee").select_option("e2e_employee")
            manager.get_by_label("External reference (optional)").fill("E2E-GRN-2071")
            manager.get_by_label("Brief (optional)").fill("Inspect carton seal and check the published procedure.")
            with manager.expect_response(lambda r: r.url.endswith("/api/backend/work/items")
                                         and r.request.method == "POST", timeout=20000) as created:
                manager.get_by_role("button", name="Queue assignment").click()
            assert created.value.status == 201, created.value.text()
            work_id = created.value.json()["id"]
            assert created.value.json()["status"] == "queued"
            employee.goto(f"{BASE}/workspace")
            expect(employee.get_by_role("heading", name="Today's work")).to_be_visible()
            expect(employee.get_by_role("link", name=re.compile("Inspect inbound pallet"))).to_be_visible(timeout=15000)
            employee.screenshot(path="/tmp/workmate-phase1-worker-assigned.png", full_page=True)
            employee.goto(f"{BASE}/work/{work_id}")
            expect(employee.get_by_role("heading", name="Inspect inbound pallet under received goods SOP")).to_be_visible()
            expect(employee.get_by_role("heading", name="Work procedure")).to_be_visible()
            expect(employee.get_by_text("No published procedure linked")).to_be_visible()
            assert outsider.request.get(f"{BASE}/api/backend/work/items/{work_id}").status == 404
            # Phase 3B acceptance: bind the generated, genuinely published
            # workflow to a real assignment and execute both source-derived steps.
            manager.goto(f"{BASE}/work/{work_id}")
            expect(manager.get_by_role("heading",name="Work procedure")).to_be_visible()
            manager.get_by_label("Published procedure").select_option(published_version)
            with manager.expect_response(
                lambda response: response.url.endswith(f"/api/backend/work/execution/{work_id}/bind")
                and response.request.method=="POST",timeout=20000,
            ) as bound:
                manager.get_by_role("button",name="Link published SOP").click()
            assert bound.value.status==200,bound.value.text()
            # Deterministic microphone fixture exercises MediaRecorder UI, upload,
            # explicit editing and confirmation. This does NOT validate Whisper WER.
            employee.add_init_script("""(() => {
                Object.defineProperty(navigator, 'mediaDevices', {
                  configurable: true,
                  value: {getUserMedia: async () => {
                    const ctx = new AudioContext();
                    return ctx.createMediaStreamDestination().stream;
                  }}
                });
                window.MediaRecorder = class SyntheticRecorder {
                  static isTypeSupported() { return true; }
                  constructor(_stream, options) {
                    this.mimeType = options?.mimeType || 'audio/webm';
                    this.state = 'inactive';
                    this.ondataavailable = null;
                    this.onstop = null;
                  }
                  start() { this.state = 'recording'; }
                  stop() {
                    if (this.state !== 'recording') return;
                    this.state = 'inactive';
                    this.ondataavailable?.({data: new Blob(['synthetic-test-audio'],
                      {type: this.mimeType})});
                    this.onstop?.();
                  }
                };
            })();""")
            employee.goto(f"{BASE}/work/{work_id}")
            expect(employee.get_by_role("button",name="Start guided work")).to_be_visible(timeout=15000)
            employee.get_by_role("button",name="Start guided work").click()
            expect(employee.get_by_text("Inspect the inbound trailer seals before unloading.")).to_be_visible(timeout=15000)
            # Phase 5A: guidance must resolve this real task's CURRENT published
            # checkpoint, cite its exact ID, and never change execution state.
            employee.get_by_role("button",name="Ask about this task").click()
            with employee.expect_response(
                lambda r:r.url.endswith("/api/backend/work/guidance/"+work_id)
                and r.request.method=="POST", timeout=20000
            ) as explained:
                employee.get_by_role("button",name="Explain this step").click()
            assert explained.value.status==200
            assert explained.value.json()["read_only"] is True
            assert explained.value.json()["citations"][0]["workflow_version_id"]==published_version
            expect(employee.get_by_text("Source-linked guidance")).to_be_visible(timeout=15000)
            # Speech preview transport is stubbed, but all session/citation checks
            # below execute through live cookie proxy, FastAPI and PostgreSQL.
            before_voice=employee.request.get(
                f"{BASE}/api/backend/work/execution/{work_id}").json()
            preview_calls=[]
            def preview_transcription(route):
                request=route.request
                assert request.method=="POST"
                assert "multipart/form-data" in request.headers.get("content-type","")
                preview_calls.append(request.url)
                route.fulfill(status=200, content_type="application/json",body=json.dumps({
                    "transcript":"Barcode को scan करो, carton damaged है?",
                    "suggested_text":"How should damaged cartons be documented?",
                    "detected_language":"hi","confidence":0.55,
                    "transcription_ms":5,"translation_ms":3,
                    "requires_confirmation":True,
                    "warning":"Review names and safety terms before sending.",
                }))
            employee.route("**/api/backend/copilot/voice/transcribe",preview_transcription)
            expect(employee.get_by_role("button",name="Record task question")).to_be_enabled()
            employee.get_by_role("button",name="Record task question").click()
            expect(employee.get_by_role("button",name="Stop recording question")).to_be_visible()
            employee.get_by_role("button",name="Stop recording question").click()
            expect(employee.get_by_label("Voice transcript review")).to_be_visible(timeout=15000)
            expect(employee.get_by_text("Barcode को scan करो, carton damaged है?")).to_be_visible()
            expect(employee.get_by_text("Speech recognition is uncertain",exact=False)).to_be_visible()
            assert len(preview_calls)==1
            assert employee.request.get(f"{BASE}/api/backend/work/execution/{work_id}").json()==before_voice
            # No voice processing or transcript preview writes to the task.
            employee.get_by_label("Editable question · suggested English").fill(
                "How should damaged cartons be documented under this SOP?"
            )
            employee.get_by_role("button",name="Use this question").click()
            expect(employee.get_by_label("Question about this task")).to_have_value(
                "How should damaged cartons be documented under this SOP?"
            )
            assert employee.request.get(f"{BASE}/api/backend/work/execution/{work_id}").json()==before_voice
            with employee.expect_response(
                lambda response: response.url.endswith("/api/backend/work/guidance/"+work_id)
                and response.request.method=="POST",timeout=20000,
            ) as confirmed_voice_guidance:
                employee.get_by_role("button",name="Ask task question").click()
            assert confirmed_voice_guidance.value.status==200
            voice_answer=confirmed_voice_guidance.value.json()
            assert voice_answer["read_only"] is True
            assert voice_answer["workflow_version_id"]==published_version
            assert voice_answer["citations"]
            assert employee.request.get(f"{BASE}/api/backend/work/execution/{work_id}").json()==before_voice
            employee.screenshot(path="/tmp/workmate-phase5b-confirmed-task-voice.png",full_page=True)
            # Department isolation remains enforced after spoken and typed queries.
            assert outsider.request.post(f"{BASE}/api/backend/work/guidance/{work_id}",
                                         data={"intent":"ask","question":"What is the current SOP?"}).status in (403,404)
            employee.unroute("**/api/backend/copilot/voice/transcribe")
            employee.evaluate("window.scrollTo(0,0)")
            employee.screenshot(path="/tmp/workmate-phase5a-task-guidance.png",full_page=True)
            employee.get_by_role("button",name="What evidence is required?").click()
            expect(employee.get_by_text("no additional mandatory attachment",exact=False)).to_be_visible(timeout=15000)
            assert outsider.request.post(
                f"{BASE}/api/backend/work/guidance/{work_id}",
                data={"intent":"current_step"}
            ).status in (403,404)
            employee.get_by_text("I confirm I performed this checkpoint").click()
            employee.get_by_role("button",name="Record checkpoint").click()
            expect(employee.get_by_text("Record visible carton damage for the shift supervisor.")).to_be_visible(timeout=15000)
            employee.get_by_role("button",name="Ask about this task").click()
            employee.get_by_role("button",name="What evidence is required?").click()
            expect(employee.get_by_text("JPEG photograph",exact=False)).to_be_visible(timeout=15000)
            employee.get_by_label("Recorded observation").fill("Carton condition documented in receiving bay.")
            proof_bytes=io.BytesIO()
            Image.effect_noise((160,160),32).convert("RGB").save(proof_bytes,format="JPEG",quality=85)
            employee.locator('input[type="file"]').set_input_files({
                "name":"checked-cartons.jpg","mimeType":"image/jpeg",
                "buffer":proof_bytes.getvalue(),
            })
            employee.get_by_role("button",name="Record checkpoint").click()
            expect(employee.get_by_text("What outcome was observed at the end of this procedure?")).to_be_visible(timeout=15000)
            employee.get_by_text("Expected outcome recorded").click()
            employee.get_by_role("button",name="Record decision").click()
            expect(employee.get_by_text("Published workflow completed")).to_be_visible(timeout=15000)
            employee.evaluate("window.scrollTo(0,0)")
            employee.screenshot(path="/tmp/workmate-phase3b-worker-execution.png",full_page=True)
            assert outsider.request.get(
                f"{BASE}/api/backend/work/execution/{work_id}"
            ).status==404
            # Phase 4A: the unsafe outcome remains blocked and creates an
            # actual task-linked case, reviewed by a separate supervisor.
            manager.goto(f"{BASE}/control-room")
            manager.get_by_role("button",name="New assignment").click()
            manager.get_by_label("Task title").fill("Inspect exception cartons at inbound bay")
            manager.get_by_label("Work type").select_option("receiving")
            manager.get_by_label("Priority").select_option("high")
            manager.get_by_label("Assign employee").select_option("e2e_employee")
            with manager.expect_response(
                lambda response: response.url.endswith("/api/backend/work/items")
                and response.request.method=="POST",timeout=20000,
            ) as exception_task:
                manager.get_by_role("button",name="Queue assignment").click()
            assert exception_task.value.status==201
            exception_work_id=exception_task.value.json()["id"]
            manager.goto(f"{BASE}/work/{exception_work_id}")
            manager.get_by_label("Published procedure").select_option(published_version)
            with manager.expect_response(
                lambda r: r.url.endswith("/api/backend/work/execution/"+exception_work_id+"/bind")
                and r.request.method=="POST", timeout=20000
            ) as linked:
                manager.get_by_role("button",name="Link published SOP").click()
            assert linked.value.status==200
            employee.goto(f"{BASE}/work/{exception_work_id}")
            employee.get_by_role("button",name="Start guided work").click()
            expect(employee.get_by_text("Inspect the inbound trailer seals before unloading.")).to_be_visible()
            employee.get_by_text("I confirm I performed this checkpoint").click()
            employee.get_by_role("button",name="Record checkpoint").click()
            expect(employee.get_by_text("Record visible carton damage for the shift supervisor.")).to_be_visible()
            employee.get_by_label("Recorded observation").fill("Damaged corner carton photographed and held.")
            employee.locator('input[type="file"]').set_input_files({
                "name":"exception-cartons.jpg","mimeType":"image/jpeg",
                "buffer":proof_bytes.getvalue(),
            })
            employee.get_by_role("button",name="Record checkpoint").click()
            expect(employee.get_by_text("What outcome was observed at the end of this procedure?")).to_be_visible()
            employee.get_by_text("An exception was documented").click()
            with employee.expect_response(
                lambda r: r.url.endswith("/api/backend/work/execution/"+exception_work_id+"/decision")
                and r.request.method=="POST",timeout=20000
            ) as exceptional:
                employee.get_by_role("button",name="Record decision").click()
            assert exceptional.value.status==200
            assert exceptional.value.json()["status"]=="blocked"
            # Phase 4B: source worker files an authentic shift handover using
            # the bound, paused SOP session; no manual conversation ID supplied.
            expect(employee.get_by_label("Required next-shift action")).to_be_visible(timeout=15000)
            employee.get_by_label("Required next-shift action").fill(
                "Keep damaged cartons quarantined and review photos at next shift."
            )
            employee.get_by_label("Context (optional)").fill(
                "Damaged corner documented in the second receiving checkpoint."
            )
            with employee.expect_response(
                lambda r: "/api/backend/work/exceptions/" in r.url
                and r.url.endswith("/handover") and r.request.method=="POST",
                timeout=20000
            ) as handover_created:
                employee.get_by_role("button",name="Submit linked shift handover").click()
            assert handover_created.value.status==201
            linked_handover=handover_created.value.json()["handover_id"]
            expect(employee.get_by_text("Shift handover saved:",exact=False)).to_be_visible(timeout=15000)
            employee.reload()
            expect(employee.get_by_text("Shift handover saved:",exact=False)).to_be_visible(timeout=15000)
            expect(employee.get_by_role("button",name="Submit linked shift handover")).not_to_be_visible()
            employee.evaluate("window.scrollTo(0,0)")
            employee.screenshot(path="/tmp/workmate-phase4b-worker-handover.png",full_page=True)
            assert employee.request.post(
                f"{BASE}/api/backend/work/execution/{exception_work_id}/resume",
                headers={"Origin":BASE}
            ).status==409
            assert outsider.request.get(
                f"{BASE}/api/backend/work/execution/{exception_work_id}"
            ).status==404
            manager.goto(f"{BASE}/work/exceptions")
            expect(manager.get_by_role("heading",name="Task exceptions")).to_be_visible(timeout=15000)
            manager.get_by_role("button",name=re.compile("Inspect exception cartons")).click()
            expect(manager.get_by_text("Execution remains blocked")).to_be_visible()
            manager.screenshot(path="/tmp/workmate-phase4a-supervisor-case.png",full_page=True)
            case_list=manager.request.get(f"{BASE}/api/backend/work/exceptions").json()["items"]
            task_case=next(c for c in case_list if c["work_item_id"]==exception_work_id)
            assert task_case["severity"]=="critical" and task_case["status"]=="open"
            assert task_case["handover_id"]==linked_handover
            expect(manager.get_by_text("Linked handover:",exact=False)).to_be_visible()
            assert employee.request.get(
                f"{BASE}/api/backend/work/exceptions/{task_case['id']}"
            ).status==403
            with manager.expect_response(
                lambda r: r.url.endswith("/api/backend/work/exceptions/"+task_case["id"]+"/claim")
                and r.request.method=="POST",timeout=20000
            ) as claimed_case:
                manager.get_by_role("button",name="Take ownership").click()
            assert claimed_case.value.status==200
            expect(manager.get_by_role("button",name="Take ownership")).not_to_be_visible(timeout=15000)
            manager.get_by_label("Supervisor review note").fill(
                "Quarantine the damaged goods; assign physical QA review next shift."
            )
            expect(manager.get_by_role("button",name="Request follow-up")).to_be_enabled(timeout=15000)
            with manager.expect_response(
                lambda r: r.url.endswith("/api/backend/work/exceptions/"+task_case["id"]+"/review")
                and r.request.method=="POST",timeout=20000
            ) as case_review:
                manager.get_by_role("button",name="Request follow-up").click()
            assert case_review.value.status==200
            assert case_review.value.json()["status"]=="follow_up_requested"
            manager.get_by_label("Operational action note").fill(
                "Goods isolated in receiving bay four with shift supervisor informed."
            )
            with manager.expect_response(
                lambda r: r.url.endswith("/api/backend/work/exceptions/"+task_case["id"]+"/action")
                and r.request.method=="POST",timeout=20000
            ) as contained:
                manager.get_by_role("button",name="Record containment").click()
            assert contained.value.status==200
            # The UI reloads the case and its audit trail asynchronously;
            # await the persisted containment before proposing remediation.
            expect(manager.get_by_text("containment recorded",exact=True)).to_be_visible(timeout=15000)
            manager.get_by_label("Operational action note").fill(
                "Schedule authorized site QA inspection and independent written sign-off."
            )
            expect(manager.get_by_role("button",name="Propose remediation")).to_be_enabled(timeout=15000)
            with manager.expect_response(
                lambda r: r.url.endswith("/api/backend/work/exceptions/"+task_case["id"]+"/action")
                and r.request.method=="POST",timeout=20000
            ) as proposal:
                manager.get_by_role("button",name="Propose remediation").click()
            assert proposal.value.status==200
            expect(manager.get_by_text("remediation proposed",exact=True)).to_be_visible(timeout=15000)
            manager.evaluate("window.scrollTo(0,0)")
            manager.screenshot(path="/tmp/workmate-phase4b-supervisor-continuity.png",full_page=True)
            assert manager.request.get(
                f"{BASE}/api/backend/work/exceptions/{task_case['id']}"
            ).json()["handover_id"]==linked_handover
            assert manager.request.get(
                f"{BASE}/api/backend/work/execution/{exception_work_id}"
            ).json()["status"]=="blocked"
            # Phase 4C: only the assigned case owner may propose a separate
            # published-SOP task. A different admin authorizes it.
            manager.get_by_label("Published corrective SOP").select_option(published_version)
            manager.get_by_label("Corrective worker").select_option("e2e_employee")
            manager.get_by_label("Scope and verification plan").fill(
                "Reinspect quarantined cartons using the versioned receiving SOP, "
                "capture new photographic evidence, and retain the original hold."
            )
            with manager.expect_response(
                lambda r: r.url.endswith("/api/backend/work/exceptions/"+task_case["id"]+"/corrective")
                and r.request.method=="POST",timeout=20000
            ) as proposed:
                manager.get_by_role("button",name="Submit for independent authorization").click()
            assert proposed.value.status==201, proposed.value.text()
            request_id=proposed.value.json()["id"]
            expect(manager.get_by_text("Request pending")).to_be_visible(timeout=15000)
            assert manager.request.post(
                f"{BASE}/api/backend/work/exceptions/{task_case['id']}/corrective/{request_id}/decision",
                data={"decision":"approved","decision_note":"Untrusted manager approval attempt"}
            ).status==403
            admin.goto(f"{BASE}/work/exceptions")
            admin.get_by_role("button",name=re.compile("Inspect exception cartons")).click()
            expect(admin.get_by_text("Request pending")).to_be_visible(timeout=15000)
            admin.get_by_label("Independent decision and controls").fill(
                "A separate corrective checklist is authorized; all old quarantined "
                "items stay on hold pending physical QA and site sign-off."
            )
            with admin.expect_response(
                lambda r: r.url.endswith(
                    "/api/backend/work/exceptions/"+task_case["id"]+"/corrective/"+request_id+"/decision")
                and r.request.method=="POST",timeout=20000
            ) as authorized:
                admin.get_by_role("button",name="Authorize new task").click()
            assert authorized.value.status==200,authorized.value.text()
            fresh_work_id=authorized.value.json()["corrective_work_id"]
            expect(admin.get_by_text("Request approved")).to_be_visible(timeout=15000)
            expect(admin.get_by_role("link",name="Open new corrective assignment")).to_be_visible()
            admin.evaluate("window.scrollTo(0,0)")
            admin.screenshot(path="/tmp/workmate-phase4c-independent-approval.png",full_page=True)
            response=employee.request.get(
                f"{BASE}/api/backend/work/execution/{fresh_work_id}"
            )
            assert response.status==200
            assert response.json()["status"]=="ready"
            employee.goto(f"{BASE}/work/{fresh_work_id}")
            employee.get_by_role("button",name="Start guided work").click()
            fresh_execution=employee.request.get(
                f"{BASE}/api/backend/work/execution/{fresh_work_id}"
            ).json()
            old_execution=manager.request.get(
                f"{BASE}/api/backend/work/execution/{exception_work_id}"
            ).json()
            assert fresh_execution["status"]=="active"
            assert fresh_execution["session_id"]!=old_execution["session_id"]
            assert old_execution["status"]=="blocked"
            employee.evaluate("window.scrollTo(0,0)")

            employee.screenshot(path="/tmp/workmate-phase4c-corrective-worker.png",full_page=True)
            # Phase 4D: finish the separately approved corrective SOP with a
            # genuine new execution, typed observation and real JPEG attachment.
            # A completed task alone cannot close the original incident.
            premature_review=manager.request.post(
                f"{BASE}/api/backend/work/exceptions/{task_case['id']}/closure/evidence",
                data={"expected_revision":7,"review_note":"No corrective evidence has been completed yet."},
                headers={"Origin":BASE},
            )
            assert premature_review.status==409,(premature_review.status,premature_review.text())
            employee.get_by_text("I confirm I performed this checkpoint").click()
            employee.get_by_role("button",name="Record checkpoint").click()
            expect(employee.get_by_text("Record visible carton damage for the shift supervisor.")).to_be_visible()
            employee.get_by_label("Recorded observation").fill(
                "Corrective reinspection performed, carton kept in segregation and evidence logged."
            )
            employee.locator('input[type="file"]').set_input_files({
                "name":"corrective-inspection.jpg","mimeType":"image/jpeg",
                "buffer":proof_bytes.getvalue(),
            })
            employee.get_by_role("button",name="Record checkpoint").click()
            employee.get_by_text("Expected outcome recorded").click()
            employee.get_by_role("button",name="Record decision").click()
            expect(employee.get_by_text("Published workflow completed")).to_be_visible()
            assert employee.request.get(f"{BASE}/api/backend/work/execution/{fresh_work_id}").json()["status"]=="completed"
            manager.goto(f"{BASE}/work/exceptions")
            manager.get_by_role("button",name=re.compile("Inspect exception cartons")).click()
            expect(manager.get_by_text("Corrective SOP task: completed",exact=False)).to_be_visible(timeout=15000)
            manager.get_by_label("Corrective evidence review").fill(
                "Observed completed corrective steps and retained new carton photograph; "
                "physical site acceptance still requires independent inspection."
            )
            with manager.expect_response(
                lambda response: response.url.endswith("/api/backend/work/exceptions/"+task_case["id"]+"/closure/evidence")
                and response.request.method=="POST",timeout=20000
            ) as evidence_review:
                manager.get_by_role("button",name="Record independent evidence review").click()
            assert evidence_review.value.status==201,evidence_review.value.text()
            expect(manager.get_by_text("Evidence review recorded",exact=False)).to_be_visible(timeout=15000)
            # The authorizing admin must NOT be their own final site signer.
            case_after_review=manager.request.get(
                f"{BASE}/api/backend/work/exceptions/{task_case['id']}").json()
            rejected_admin=admin.request.post(
                f"{BASE}/api/backend/work/exceptions/{task_case['id']}/closure/site",
                headers={"Origin":BASE},
                data={"expected_revision":case_after_review["revision"],
                      "site_record_reference":"E2E-SITE-QA-2071",
                      "site_acceptance_note":"Personally inspected quarantined receiving cartons after corrective SOP.",
                      "independent_site_inspection_attested":True},
            )
            assert rejected_admin.status==409,rejected_admin.text()
            assert outsider.request.get(
                f"{BASE}/api/backend/work/exceptions/{task_case['id']}").status==403
            site_admin = sign_in(browser,"e2e_site_admin@workmate.test")
            site_admin.goto(f"{BASE}/work/exceptions")
            site_admin.get_by_role("button",name=re.compile("Inspect exception cartons")).click()
            expect(site_admin.get_by_label("External inspection record ID")).to_be_visible(timeout=15000)
            site_admin.get_by_label("External inspection record ID").fill("E2E-SITE-QA-2071")
            site_admin.get_by_label("Actual site inspection findings").fill(
                "Synthetic controlled-site inspection attestation: receiving bay checked; "
                "quarantine maintained and corrective records independently accepted."
            )
            site_admin.get_by_text("I independently inspected the site",exact=False).click()
            with site_admin.expect_response(
                lambda response: response.url.endswith("/api/backend/work/exceptions/"+task_case["id"]+"/closure/site")
                and response.request.method=="POST",timeout=20000
            ) as site_accepted:
                site_admin.get_by_role("button",name="Record site acceptance and close case").click()
            assert site_accepted.value.status==200,site_accepted.value.text()
            assert site_accepted.value.json()["status"]=="closed"
            expect(site_admin.get_by_text("Site acceptance recorded",exact=False)).to_be_visible(timeout=15000)
            site_admin.screenshot(path="/tmp/workmate-phase4d-governed-closure.png",full_page=True)
            assert manager.request.get(
                f"{BASE}/api/backend/work/execution/{exception_work_id}").json()["status"]=="blocked"
            assert manager.request.get(
                f"{BASE}/api/backend/work/exceptions/{task_case['id']}").json()["status"]=="closed"
            assert manager.request.post(
                f"{BASE}/api/backend/work/exceptions/{task_case['id']}/closure/evidence",
                headers={"Origin":BASE},
                data={"expected_revision":case_after_review["revision"],
                      "review_note":"Duplicate evidence review should be rejected."}
            ).status==409
            manager.goto(f"{BASE}/control-room")
            manager.screenshot(path="/tmp/workmate-phase1-control-room.png", full_page=True)
            manager.goto(f"{BASE}/pilot")
            expect(manager.get_by_role("heading", name="Pilot review")).to_be_visible()
            # Pilot feedback stays behind real HttpOnly sessions and the
            # explicit e2e_ops cohort; outsiders must see 404.
            posted = employee.evaluate("""async () => {
                const response = await fetch('/api/backend/pilot/feedback', {
                    method: 'POST', headers: {'Content-Type':'application/json'},
                    body: JSON.stringify({surface:'reference',verdict:'needs_review',issue:'missing_evidence'})
                });
                return response.status;
            }""")
            assert posted == 201
            outsider_status = outsider.evaluate("""async () => {
                const response = await fetch('/api/backend/pilot/feedback', {
                    method: 'POST', headers: {'Content-Type':'application/json'},
                    body: JSON.stringify({surface:'reference',verdict:'helpful',issue:'none'})
                });
                return response.status;
            }""")
            assert outsider_status == 404
            admin.goto(f"{BASE}/pilot")
            expect(admin.get_by_role("heading", name="Pilot review")).to_be_visible()
            expect(admin.get_by_text("reference · missing evidence")).to_be_visible(timeout=20000)
            # Draft must not be visible to either employee.
            search_sources(employee, expected=False)
            search_sources(outsider, expected=False)

            before_approval = ask_reference(employee, "security seal damaged cartons quarantine")
            assert before_approval["requires_escalation"] and not before_approval["citations"], before_approval

            # Browser sessions carry real access tokens, never fake provider mocks.
            # Browser JavaScript must never have a bearer or refresh credential.
            assert employee.evaluate("localStorage.getItem('token')") is None
            assert employee.evaluate("localStorage.getItem('refresh_token')") is None
            browser_cookies = employee.context.cookies([BASE])
            assert any(c["name"] == "wm_access" and c["httpOnly"] for c in browser_cookies)
            assert any(c["name"] == "wm_refresh" and c["httpOnly"] for c in browser_cookies)
            forbidden_status = employee.evaluate("""async () => {
                const response = await fetch('/api/backend/knowledge/references?department_id=e2e_ops');
                return response.status;
            }""")
            assert forbidden_status == 403

            # CSRF: foreign Origin never allowed to mutate even with valid cookie.
            # A browser cannot override the forbidden Origin header in fetch.
            # The context request shares the session cookie and can simulate a
            # hostile cross-site form request with an explicit foreign Origin.
            csrf_attempt = employee.request.post(
                f"{BASE}/api/session/logout",
                headers={"Origin": "https://attacker.example"},
            )
            assert csrf_attempt.status == 403

            admin.goto(f"{BASE}/knowledge-studio/references")
            expect(admin.get_by_role("heading", name="Reference library")).to_be_visible()
            admin.locator("select").select_option("e2e_ops")
            admin.get_by_role("button", name=DOCUMENT_NAME).click()
            expect(admin.get_by_role("heading", name=DOCUMENT_NAME)).to_be_visible(timeout=20000)
            admin.once("dialog", lambda d: d.accept())
            admin.get_by_role("button", name="Approve for search").click()
            expect(admin.get_by_text("APPROVED", exact=True)).to_be_visible(timeout=30000)
            search_sources(employee, expected=True)
            search_sources(outsider, expected=False)
            approved_answer = ask_reference(
                employee, "security seal damaged cartons quarantine goods supervisor",
            )
            assert approved_answer["is_grounded"], approved_answer
            assert not approved_answer["requires_escalation"], approved_answer
            assert approved_answer["citations"], approved_answer
            assert all(item["source_type"] == "reference"
                       and item["document_title"] == DOCUMENT_NAME
                       and item["excerpt"] in DOCUMENT_TEXT
                       for item in approved_answer["citations"]), approved_answer
            verify_history_resume(employee, approved_answer["conversation_id"])
            # Shift handover is read-only; the reviewer exports an explicit
            # local draft from a real saved conversation and workflow status.
            employee.goto(f"{BASE}/copilot/handover")
            expect(employee.get_by_role("heading", name="Pass on the context, not the confusion.")).to_be_visible()
            chosen_session = employee.locator("#handover-session")
            expect(chosen_session.locator(f'option[value="{approved_answer["conversation_id"]}"]')).to_be_attached(timeout=15000)
            chosen_session.select_option(approved_answer["conversation_id"])
            employee.get_by_label("What needs to happen next?").fill("Verify damaged cartons before the next shift.")
            handover_download = employee.get_by_role("button", name="Download .txt")
            expect(handover_download).to_be_enabled(timeout=15000)
            with employee.expect_download() as exported:
                handover_download.click()
            handover_file = exported.value.path()
            handover_body = handover_file.read_text(encoding="utf-8")
            employee.evaluate("window.scrollTo(0,0)")
            employee.screenshot(path="/tmp/workmate-eval-shift-handover.png", full_page=True)
            assert "Verify damaged cartons before the next shift." in handover_body
            assert approved_answer["conversation_id"] in handover_body
            assert "not an approved policy" in handover_body.lower()
            employee.get_by_label("Next shift / recipient").fill("Night shift lead")
            employee.locator("#handover-exception").select_option("damage")
            employee.locator("#handover-severity").select_option("high")
            with employee.expect_response(lambda r: r.url.endswith("/api/backend/handover")
                                          and r.request.method == "POST", timeout=20000) as saved:
                employee.get_by_role("button", name="Submit for review").click()
            assert saved.value.status == 201, saved.value.text()
            handover_id = saved.value.json()["id"]
            assert handover_id.startswith("hov_")
            # Only a manager from this department can review; employee and
            # foreign-department browsers cannot use reviewer permissions.
            assert employee.request.post(
                f"{BASE}/api/backend/handover/{handover_id}/review",
                data={"decision":"acknowledged","review_note":"Reviewed by employee"}
            ).status == 403
            outsider.goto(f"{BASE}/handover/review")
            outsider.wait_for_url("**/workspace", timeout=12000)
            manager.goto(f"{BASE}/handover/review")
            expect(manager.get_by_role("heading", name="Shift handover queue")).to_be_visible()
            # The linked Phase 4B incident handover also appears here.
            # Target the independent legacy handover by its recipient rather
            # than clicking the first of multiple valid claim buttons.
            target_handover=manager.locator("article").filter(has_text="Night shift lead")
            with manager.expect_response(
                lambda r: r.url.endswith("/api/backend/handover/" + handover_id + "/claim")
                and r.request.method == "POST", timeout=20000,
            ) as claim_reply:
                target_handover.get_by_role("button", name="Take ownership").click()
            assert claim_reply.value.status == 200, claim_reply.value.text()
            assert claim_reply.value.json()["assigned_to_user_id"]
            manager.evaluate("window.scrollTo(0,0)")
            manager.screenshot(path="/tmp/workmate-eval-manager-queue.png", full_page=True)
            target_handover.get_by_label("Reviewer note (required)").fill(
                "Keep the damaged cartons separated until reviewed.")
            with manager.expect_response(
                lambda r: r.url.endswith("/api/backend/handover/" + handover_id + "/review")
                and r.request.method == "POST", timeout=20000,
            ) as reviewed:
                target_handover.get_by_role("button", name="Request follow-up").click()
            assert reviewed.value.status == 200, reviewed.value.text()
            assert reviewed.value.json()["status"] == "follow_up_requested"
            # Explicitly review the *linked* task handover independently.
            linked_card=manager.locator("article").filter(has_text="Next-shift supervisor")
            with manager.expect_response(
                lambda r: r.url.endswith("/api/backend/handover/"+linked_handover+"/claim")
                and r.request.method=="POST",timeout=20000
            ) as linked_claim:
                linked_card.get_by_role("button",name="Take ownership").click()
            assert linked_claim.value.status==200
            expect(linked_card.get_by_label("Reviewer note (required)")).to_be_visible(timeout=15000)
            linked_card.get_by_label("Reviewer note (required)").fill(
                "Acknowledged shift context; cartons stay quarantined for independent QA."
            )
            with manager.expect_response(
                lambda r: r.url.endswith("/api/backend/handover/"+linked_handover+"/review")
                and r.request.method=="POST",timeout=20000
            ) as linked_review:
                linked_card.get_by_role("button",name="Acknowledge receipt").click()
            assert linked_review.value.status==200
            assert linked_review.value.json()["status"]=="acknowledged"
            case_after_handover=manager.request.get(
                f"{BASE}/api/backend/work/exceptions/{task_case['id']}"
            ).json()
            assert case_after_handover["handover_status"]=="acknowledged"
            assert case_after_handover["work_status"]=="blocked"
            outsider_answer = ask_reference(
                outsider, "security seal damaged cartons quarantine goods supervisor",
            )
            assert outsider_answer["requires_escalation"] and not outsider_answer["citations"]

            admin.goto(f"{BASE}/knowledge-studio/references")
            admin.locator("select").select_option("e2e_ops")
            admin.get_by_role("button", name=DOCUMENT_NAME).click()
            expect(admin.get_by_role("heading", name=DOCUMENT_NAME)).to_be_visible(timeout=20000)
            admin.once("dialog", lambda d: d.accept())
            admin.get_by_role("button", name="Archive document").click()
            expect(admin.get_by_text("ARCHIVED", exact=True)).to_be_visible(timeout=30000)
            search_sources(employee, expected=False)
            archived_answer = ask_reference(
                employee, "security seal damaged cartons quarantine goods supervisor",
            )
            assert archived_answer["requires_escalation"] and not archived_answer["citations"], archived_answer
            # Phase 2: a real published compiled state graph and required JPEG proof.
            # This synthetic SOP is inserted into *disposable test DB only*.
            manager.goto(f"{BASE}/control-room")
            manager.get_by_role("button",name="New assignment").click()
            manager.get_by_label("Task title").fill("Independent checkpoint validation task")
            manager.get_by_label("Work type").select_option("receiving")
            manager.get_by_label("Assign employee").select_option("e2e_employee")
            with manager.expect_response(
                lambda r: r.url.endswith("/api/backend/work/items")
                and r.request.method=="POST",timeout=20000
            ) as second_task:
                manager.get_by_role("button",name="Queue assignment").click()
            assert second_task.value.status==201
            phase2_work_id=second_task.value.json()["id"]
            seeded_version=seed_published_execution_fixture()
            manager.goto(f"{BASE}/work/{phase2_work_id}")
            expect(manager.get_by_role("heading",name="Work procedure")).to_be_visible()
            manager.get_by_label("Published procedure").select_option(seeded_version)
            with manager.expect_response(
                lambda r: r.url.endswith(f"/api/backend/work/execution/{phase2_work_id}/bind")
                and r.request.method=="POST", timeout=20000,
            ) as bound:
                manager.get_by_role("button",name="Link published SOP").click()
            assert bound.value.status==200,bound.value.text()
            employee.goto(f"{BASE}/work/{phase2_work_id}")
            expect(employee.get_by_role("button",name="Start guided work")).to_be_visible()
            with employee.expect_response(
                lambda r: r.url.endswith(f"/api/backend/work/execution/{phase2_work_id}/start")
                and r.request.method=="POST", timeout=20000,
            ) as started:
                employee.get_by_role("button",name="Start guided work").click()
            assert started.value.status==200,started.value.text()
            session_id=started.value.json()["session_id"]
            # Task sessions cannot be advanced through the legacy chat endpoint.
            bypass=employee.request.post(
                f"{BASE}/api/backend/copilot/session/{session_id}/advance",
                headers={"Origin":BASE},data={"values":{}}
            )
            assert bypass.status==403,bypass.text()
            employee.get_by_role("button",name="Pause work").click()
            expect(employee.get_by_text("Work paused",exact=True)).to_be_visible()
            employee.get_by_role("button",name="Resume execution").click()
            expect(employee.get_by_text("Inspect the inbound seal")).to_be_visible()
            expect(employee.get_by_role("button",name="Record checkpoint")).to_be_disabled()
            employee.get_by_text("I confirm I performed this checkpoint").click()
            employee.get_by_role("button",name="Record checkpoint").click()
            expect(employee.get_by_text("Record carton condition and attach a photo")).to_be_visible()
            expect(employee.get_by_role("button",name="Record checkpoint")).to_be_disabled()
            photo_buffer=io.BytesIO()
            Image.new("RGB",(8,8),(140,180,130)).save(photo_buffer,format="JPEG")
            employee.get_by_label("Recorded observation").fill("Carton intact at the receiving bay.")
            employee.locator("#file-e2e_photo_spec").set_input_files({
                "name":"synthetic-carton.jpg",
                "mimeType":"image/jpeg",
                "buffer":photo_buffer.getvalue(),
            })
            with employee.expect_response(
                lambda r: r.url.endswith(f"/api/backend/work/execution/{phase2_work_id}/step")
                and r.request.method=="POST", timeout=20000,
            ) as evidence:
                employee.get_by_role("button",name="Record checkpoint").click()
            assert evidence.value.status==200,evidence.value.text()
            employee.locator('section[aria-labelledby="work-execution-title"]').screenshot(path="/tmp/workmate-phase2-decision.png")
            expect(employee.get_by_role("heading",name="Condition assessment")).to_be_visible()
            employee.get_by_text("Accept and finish").click()
            employee.get_by_role("button",name="Record decision").click()
            expect(employee.get_by_text("Published workflow completed")).to_be_visible()
            employee.locator('section[aria-labelledby="work-execution-title"]').screenshot(path="/tmp/workmate-phase2-completed.png")
            summary=employee.request.get(f"{BASE}/api/backend/work/execution/{phase2_work_id}").json()
            assert summary["status"]=="completed" and summary["completed_steps"]==2
            assert outsider.request.get(
                f"{BASE}/api/backend/work/execution/{phase2_work_id}"
            ).status==404
            logout = employee.request.post(
                f"{BASE}/api/session/logout", headers={"Origin": BASE}
            )
            assert logout.status == 200
            assert employee.evaluate("async () => (await fetch('/api/session/me')).status") == 401
            print("BROWSER PASSED: real published SOP binding, step confirmation, required JPEG evidence, decision completion, session bypass denial, tenant isolation; reference and handover regression.")
        except Exception:
            for name, page in [("admin", admin), ("employee", employee), ("outsider", outsider), ("manager", manager), ("site_admin", site_admin)]:
                if page is not None:
                    page.screenshot(path=f"/tmp/workmate-{name}-failure.png", full_page=True)
            raise
        finally:
            browser.close()


if __name__ == "__main__":
    main()
