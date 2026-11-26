# Acceptance scenarios A–J (English-only build)

Run: `WORKMATE_RUN_LIVE_TESTS=1 DATABASE_URL=postgresql://…@127.0.0.1:5432/workmate PYTHONPATH=backend:backend/tests python -m pytest backend/tests/test_scenarios_postgres.py backend/tests/test_knowledge_loop_postgres.py backend/tests/test_tenant_knowledge_isolation_postgres.py`

Every scenario drives the real FastAPI stack with real signed tokens against a **scratch PostgreSQL database** created and
dropped per test (all migrations applied, 85 demo SOPs published). Only scenario H mocks anything, and only the failure being tested.
Last full-suite result: **550 passed, 1 skipped, 0 failed**.

| # | Scenario | Test | Result |
|---|---|---|---|
| A | Employee asks how to receive a shipment, gets a cited answer, starts the approved workflow, completes permitted steps | `test_A_employee_guidance_cited_answer_and_permitted_steps` | Pass. Nothing starts without a "yes"; a step question is answered from the SOP with a citation; "go to step 4" is refused; the workflow completes only through explicit attestation and the observed-outcome decision |
| B | Hindi voice | `test_B_hindi_voice_is_out_of_scope_and_absent` | **Removed from scope** (English-only decision); the test asserts the voice endpoints no longer exist |
| C | "Sir, shipment mein do boxes missing hain" → exception → routed | `test_C_hinglish_discrepancy_creates_an_authorised_exception`, `test_C_failure_to_save_is_reported_honestly` | Pass. Proposal first ("2 boxes… does not adjust stock, contact the supplier or close the PO"), record written only after "yes", exactly once, visible to the manager who can claim it; missing quantity is asked; "no" writes nothing; a failed save says "nothing was sent" |
| D | Missing knowledge → escalation → admin reply → SOP drafted, reviewed, published | `test_knowledge_loop_postgres.py` (2 tests) | Pass, plus a re-run of all migrations on the resulting data |
| E | Admin uploads a document → extracted steps reviewed → manager approval → publish → employee retrieves the right version | `test_E_admin_uploads_a_document_through_review_and_approval_to_employee_retrieval` | Pass. Not retrievable before publication; unreviewed steps cannot be marked reviewed; publish blocked until a manager approves; another company cannot retrieve it |
| F | Manager reviews an open exception, assigns corrective work, verifies, closes; employee is updated | `test_F_manager_intervention_to_closure_and_employee_updates` | Pass. Worker report → claim → review → containment → remediation plan → corrective request (manager) → approval (a *different* person, admin) → corrective work by another employee with a photo → evidence review → site acceptance by a third, independent admin → closed. The reporting employee sees plain progress at every stage and never internal notes; replays are rejected |
| G | Cross-organization access denied without leaking | `test_G_cross_organization_access_is_denied_without_leaking`, `test_tenant_knowledge_isolation_postgres.py` | Pass. Another company's SOP is not retrieved, cited or named; its knowledge, employees and gaps are 404 to the wrong admin; employees get 403 on every admin route |
| H | Ollama / database unavailable | `test_H_service_failures_are_reported_honestly_and_lose_nothing` | Pass. Unreachable model: lookup, workflow, cited follow-ups still work, no stall; a failed save says so, claims nothing, and a retry then succeeds exactly once; conversation store down returns a 5xx with no fabricated answer. *Speech* failure is moot (voice removed) |
| I | Replace an SOP; versioning policy for active workflows | `test_I_replacing_an_sop_new_questions_use_new_version_active_work_finishes_on_old` | Pass. **Policy (tested):** a session finishes on the version it started on; every new session gets the latest published version; history shows both versions and exactly one is published |
| J | Hazardous equipment fault | `test_J_safety_critical_report_stops_work_and_never_invents_repairs` | Pass. Stop-work and emergency wording, no repair instructions, one urgent case, also when a workflow is in progress |

## Defects these scenarios found and fixed
- **Analytics leaked across companies** (`G2`): the Intelligence Hub endpoints returned every company's FAQs, SOP usage, escalation
  reasons (with user ids) and adoption when no department was given. Now scoped (managers: own department; admins: own organization).
- **Workflow sessions readable and changeable by any admin of any company** (`G3`): the admin role bypassed the ownership check.
  Now only the owner can change a session; an admin can only read sessions inside their own organization; foreign ids answer 404.
- Re-running migrations failed once any SOP had been approved (migration 009 re-tightened a constraint) — a deploy-breaker.
- An unrelated "explain …" question during a workflow was answered with the current step's rule as if relevant.
- Employees could not see the status of an issue they reported (added `/work/exceptions/mine`, shown on the workspace).
- The assistant had no way to turn a spoken-style discrepancy report into a record (added a confirm-first typed action).

## Desktop sweep (Chromium, 1440×900, real backend)
All 28 role/route combinations (employee 5, manager 10, admin 13) load with no crash, no failed API call and no console error.
One unlabeled icon button was found and fixed. Flows also exercised by hand in the browser: login for all three roles, invite →
accept → sign in, unanswered question → reply → draft → review → approval → publish → employee finds it, Hinglish discrepancy
report → manager handover queue, blocked task → employee progress card → manager exception queue.

## Approval gate now covers direct uploads (E2)
`test_E2_direct_owd_upload_cannot_bypass_manager_approval`: with `PUBLISH_REQUIRES_APPROVAL=true` (default) a Knowledge Studio
file upload is validated and stored as a *pending submission*; no workflow exists and employees cannot retrieve it. Only a
manager can approve (admin and employee get 403), the same bytes cannot be queued twice, a return needs a real note and
publishes nothing, and an approval compiles and publishes exactly the stored file in one transaction (failure rolls back and
leaves it pending). Replacing an existing SOP (scenario I) goes through the same two-person path. Verified in the browser:
admin upload shows "Waiting for manager approval", the manager's Approvals page lists the file, approval publishes, the employee
then finds it.

## Responsive and accessibility sweep (desktop 1440, tablet 820, phone 390)
`backend/e2e/ui_sweep.js` (run with the Playwright MCP "run code" tool; credentials supplied locally) checks every role/route
at three widths for horizontal overflow, touch targets under 40px, unlabeled controls, nameless buttons/links, exactly one
`<h1>`, text contrast against WCAG AA (4.5:1 / 3:1 large), console errors and failed API calls.
**Result: 60 route/size combinations, 0 problems.** Fixes made to get there: 44px minimum targets on touch widths, a label on the
copilot message box, an accessible name on an icon button, darkened ~280 low-contrast text colors (about 120 failing text nodes
across the app became 0), a higher-contrast sidebar description, and a "Skip to main content" link (first Tab; Enter moves into the
page instead of through 9-18 sidebar stops). Keyboard audit: every focus stop has a visible indicator.
Not done: a screen-reader pass (NVDA/VoiceOver) and an automated axe run (downloading a script into the page was declined by the
tooling; the checks above are self-written and cover contrast, names, labels, landmarks and focus only).

## Known gaps (not hidden)
1. The assistant's catalog match used to propose loosely related SOPs on a one-word overlap; the proposal and suggestion floors
   are now 0.45 (regression tests added). Real customer SOPs with sparse descriptions may need aliases added to be found.
2. Screen-reader testing and a full axe audit have not been done.
3. Free-form answers from the language model are not part of any scenario; `qwen2.5:3b` is installed but unused by these paths.
4. Row-level security still covers only reference documents; other tenant isolation is application-level (tested, not DB-enforced).
5. The scenarios are API-level tests plus manual browser runs; there is no automated browser suite in CI.
