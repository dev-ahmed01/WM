"""True Chromium -> Next.js -> FastAPI -> PostgreSQL browser smoke.

Runs only against disposable CI services. No mocked responses, no seeded
business knowledge. Tests draft approval, immediately effective archival,
role isolation and independent departmental search.
"""
from __future__ import annotations

import os
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
        page.wait_for_url("**/knowledge-studio" if "admin" in email else "**/intelligence-hub" if "manager" in email else "**/workspace", timeout=12000)
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
            outsider = sign_in(browser, "e2e_other@workmate.test")
            manager = sign_in(browser, "e2e_manager@workmate.test")
            expect(manager.get_by_role("heading", name="Manager overview")).to_be_visible()
            manager.goto(f"{BASE}/knowledge-studio")
            manager.wait_for_url("**/intelligence-hub", timeout=12000)
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
            logout = employee.request.post(
                f"{BASE}/api/session/logout", headers={"Origin": BASE}
            )
            assert logout.status == 200
            assert employee.evaluate("async () => (await fetch('/api/session/me')).status") == 401
            print("BROWSER PASSED: reference citations and history, manager role, pilot feedback, pre/post approval/archive abstention, department isolation, CSRF and logout.")
        except Exception:
            for name, page in [("admin", admin), ("employee", employee), ("outsider", outsider), ("manager", manager)]:
                if page is not None:
                    page.screenshot(path=f"/tmp/workmate-{name}-failure.png", full_page=True)
            raise
        finally:
            browser.close()


if __name__ == "__main__":
    main()
