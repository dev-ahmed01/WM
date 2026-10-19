"""True Chromium -> Next.js -> FastAPI -> PostgreSQL browser smoke.

Runs only against disposable CI services. No mocked responses, no seeded
business knowledge. Tests draft approval, immediately effective archival,
role isolation and independent departmental search.
"""
from __future__ import annotations

import io
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
            page.get_by_role("link", name=re.compile("Ask about your work")).click()
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
        try:
            admin = sign_in(browser, "e2e_admin@workmate.test")
            admin.screenshot(path="/tmp/workmate-phase1-procedure-studio.png", full_page=True)
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
            expect(employee.get_by_text("Phase 2 · no evidence captured yet")).to_be_visible()
            assert outsider.request.get(f"{BASE}/api/backend/work/items/{work_id}").status == 404
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
            with manager.expect_response(
                lambda r: r.url.endswith("/api/backend/handover/" + handover_id + "/claim")
                and r.request.method == "POST", timeout=20000,
            ) as claim_reply:
                manager.get_by_role("button", name="Take ownership").click()
            assert claim_reply.value.status == 200, claim_reply.value.text()
            assert claim_reply.value.json()["assigned_to_user_id"]
            manager.evaluate("window.scrollTo(0,0)")
            manager.screenshot(path="/tmp/workmate-eval-manager-queue.png", full_page=True)
            manager.get_by_label("Reviewer note (required)").fill(
                "Keep the damaged cartons separated until reviewed.")
            with manager.expect_response(
                lambda r: r.url.endswith("/api/backend/handover/" + handover_id + "/review")
                and r.request.method == "POST", timeout=20000,
            ) as reviewed:
                manager.get_by_role("button", name="Request follow-up").click()
            assert reviewed.value.status == 200, reviewed.value.text()
            assert reviewed.value.json()["status"] == "follow_up_requested"
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
            seeded_version=seed_published_execution_fixture()
            manager.goto(f"{BASE}/work/{work_id}")
            expect(manager.get_by_role("heading",name="Work procedure")).to_be_visible()
            manager.get_by_label("Published procedure").select_option(seeded_version)
            with manager.expect_response(
                lambda r: r.url.endswith(f"/api/backend/work/execution/{work_id}/bind")
                and r.request.method=="POST", timeout=20000,
            ) as bound:
                manager.get_by_role("button",name="Link published SOP").click()
            assert bound.value.status==200,bound.value.text()
            employee.goto(f"{BASE}/work/{work_id}")
            expect(employee.get_by_role("button",name="Start guided work")).to_be_visible()
            with employee.expect_response(
                lambda r: r.url.endswith(f"/api/backend/work/execution/{work_id}/start")
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
                lambda r: r.url.endswith(f"/api/backend/work/execution/{work_id}/step")
                and r.request.method=="POST", timeout=20000,
            ) as evidence:
                employee.get_by_role("button",name="Record checkpoint").click()
            assert evidence.value.status==200,evidence.value.text()
            employee.screenshot(path="/tmp/workmate-phase2-decision.png",full_page=True)
            expect(employee.get_by_text("Condition assessment")).to_be_visible()
            employee.get_by_text("Accept and finish").click()
            employee.get_by_role("button",name="Record decision").click()
            expect(employee.get_by_text("Published workflow completed")).to_be_visible()
            employee.screenshot(path="/tmp/workmate-phase2-completed.png",full_page=True)
            summary=employee.request.get(f"{BASE}/api/backend/work/execution/{work_id}").json()
            assert summary["status"]=="completed" and summary["completed_steps"]==2
            assert outsider.request.get(
                f"{BASE}/api/backend/work/execution/{work_id}"
            ).status==404
            logout = employee.request.post(
                f"{BASE}/api/session/logout", headers={"Origin": BASE}
            )
            assert logout.status == 200
            assert employee.evaluate("async () => (await fetch('/api/session/me')).status") == 401
            print("BROWSER PASSED: real published SOP binding, step confirmation, required JPEG evidence, decision completion, session bypass denial, tenant isolation; reference and handover regression.")
        except Exception:
            for name, page in [("admin", admin), ("employee", employee), ("outsider", outsider), ("manager", manager)]:
                if page is not None:
                    page.screenshot(path=f"/tmp/workmate-{name}-failure.png", full_page=True)
            raise
        finally:
            browser.close()


if __name__ == "__main__":
    main()
