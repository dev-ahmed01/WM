"""Cases (requests for human help), answer feedback and conversation history, end to end on a scratch database.
Run as the database owner and as the production-style restricted runtime login."""
import pytest

from scenarios_support import DEPT_A, DEPT_B, headers
from test_knowledge_loop_postgres import scratch  # noqa: F401  (fixture)
from test_scenarios_postgres import world  # noqa: F401  (fixture)


@pytest.mark.live_integration
def test_employee_asks_a_person_staff_reply_and_employee_acknowledges(world):
    api = world
    first = api.ask("emp1", "how do I do goods receipt posting")
    conv = first["conversation_id"]
    made = api.post("emp1", "/copilot/escalate", {"conversation_id": conv, "note": "The scanner will not scan the label",
                                                  "message_ids": [first["message_id"]]})
    assert made.status_code == 201, made.text
    case = made.json()
    assert case["kind"] == "human_request" and case["public_status"] == "open"
    assert [m["kind"] for m in case["thread"]] == ["context", "message"]   # only what the employee chose to share

    # staff in scope see it; another company, another employee and the wrong role do not
    staff = api.get("admin1", "/cases?view=escalated").json()
    assert [c["id"] for c in staff["items"]] == [case["id"]] and staff["counts"]["escalated"] == 1
    assert api.get("admin_b", f"/cases/{case['id']}").status_code == 404
    assert api.get("emp2", f"/my/cases/{case['id']}").status_code == 404
    assert api.get("emp1", "/cases").status_code == 403

    # an internal note never reaches the employee; a reply does and moves the case to In progress
    note = api.post("admin1", f"/cases/{case['id']}/messages", {"body": "Check the dock scanner firmware", "internal": True})
    assert note.status_code == 201
    reply = api.post("mgr", f"/cases/{case['id']}/messages", {"body": "Restart the scanner, then rescan the label."})
    assert reply.status_code == 201
    mine = api.get("emp1", f"/my/cases/{case['id']}").json()
    assert mine["public_status"] == "in_progress"
    bodies = [m["body"] for m in mine["thread"]]
    assert "Restart the scanner, then rescan the label." in bodies and not any("firmware" in b for b in bodies)
    assert api.get("emp1", "/my/cases").json()["items"][0]["latest_reply"].startswith("Restart the scanner")
    staff_view = api.get("admin1", f"/cases/{case['id']}").json()
    assert any(m["internal"] for m in staff_view["thread"])

    # the employee adds information; staff resolve; the employee acknowledges; closed cases take no more messages
    assert api.post("emp1", f"/my/cases/{case['id']}/messages", {"body": "Still not scanning after restart"}).status_code == 201
    assert api.post("emp1", f"/my/cases/{case['id']}/acknowledge").status_code == 409      # not resolved yet
    assert api.post("admin1", f"/cases/{case['id']}/resolve", {"note": "Replaced the scanner."}).status_code == 200
    assert api.get("emp1", f"/my/cases/{case['id']}").json()["public_status"] == "resolved"
    done = api.post("emp1", f"/my/cases/{case['id']}/acknowledge")
    assert done.status_code == 200 and done.json()["public_status"] == "closed"
    assert api.post("emp1", f"/my/cases/{case['id']}/messages", {"body": "thanks"}).status_code == 409
    assert api.post("admin1", f"/cases/{case['id']}/messages", {"body": "late"}).status_code == 409
    assert api.get("admin1", "/cases?view=resolved").json()["counts"]["resolved"] == 1


@pytest.mark.live_integration
def test_cannot_raise_a_case_from_someone_elses_conversation(world):
    api = world
    conv = api.ask("emp1", "how do I do goods receipt posting")["conversation_id"]
    assert api.post("emp2", "/copilot/escalate", {"conversation_id": conv}).status_code == 404
    assert api.post("emp_b", "/copilot/escalate", {"conversation_id": conv}).status_code == 404
    assert api.get("admin1", "/cases").json()["items"] == []


@pytest.mark.live_integration
def test_not_helpful_flags_the_answer_for_staff_and_helpful_does_not(world):
    api = world
    good = api.ask("emp1", "how do I do goods receipt posting")
    r = api.post("emp1", "/copilot/feedback", {"message_id": good["message_id"], "rating": "helpful"})
    assert r.status_code == 201 and r.json()["case_id"] is None
    bad = api.ask("emp1", "what is a pallet")
    r = api.post("emp1", "/copilot/feedback", {"message_id": bad["message_id"], "rating": "not_helpful", "note": "Wrong dock"})
    assert r.status_code == 201 and r.json()["case_id"]
    again = api.post("emp1", "/copilot/feedback", {"message_id": bad["message_id"], "rating": "not_helpful"})
    assert again.json()["case_id"] is None                                    # one open case per question, not a pile
    items = api.get("admin1", "/cases?view=escalated").json()["items"]
    assert [c["kind"] for c in items] == ["incorrect_answer"]
    # you can only rate your own answers
    assert api.post("emp2", "/copilot/feedback", {"message_id": good["message_id"], "rating": "helpful"}).status_code == 404
    assert api.post("emp1", "/copilot/feedback", {"message_id": good["message_id"], "rating": "great"}).status_code == 422


@pytest.mark.live_integration
def test_assign_escalate_and_manager_view(world):
    api = world
    conv = api.ask("emp1", "how do I do goods receipt posting")["conversation_id"]
    case = api.post("emp1", "/copilot/escalate", {"conversation_id": conv, "note": "Pallet is blocked"}).json()
    assert api.get("mgr", "/cases?managed=true").json()["items"] == []            # not escalated to a manager yet
    people = api.get("admin1", "/cases/people").json()["items"]
    assert {"admin1", "mgr"} <= {p["id"] for p in people} and "emp1" not in {p["id"] for p in people}
    assert api.post("admin1", f"/cases/{case['id']}/assign", {"assignee_id": "emp1"}).status_code == 409   # staff only
    assert api.post("admin1", f"/cases/{case['id']}/assign", {"assignee_id": "admin_b"}).status_code == 409  # other company
    got = api.post("admin1", f"/cases/{case['id']}/assign", {"assignee_id": "mgr"})
    assert got.status_code == 200 and got.json()["assigned_to"] == "mgr" and got.json()["public_status"] == "in_progress"
    esc = api.post("admin1", f"/cases/{case['id']}/flags", {"escalate_to_manager": True})
    assert esc.json()["escalated_to_manager"] and esc.json()["priority"] == "high"
    assert [c["id"] for c in api.get("mgr", "/cases?managed=true").json()["items"]] == [case["id"]]
    assert api.get("admin1", "/cases?priority=high").json()["items"][0]["id"] == case["id"]
    assert api.get("admin1", "/cases?q=goods%20receipt").json()["items"][0]["id"] == case["id"]
    assert api.get("admin1", "/cases?q=zzz-nothing").json()["items"] == []


@pytest.mark.live_integration
def test_unanswered_questions_appear_as_cases_and_an_employee_can_follow_them(world):
    api = world
    api.ask("emp1", "quarantine of purple widgets in the lunar warehouse")
    unanswered = api.get("admin1", "/cases?view=unanswered").json()["items"]
    assert len(unanswered) == 1 and unanswered[0]["kind"] == "unanswered" and unanswered[0]["public_status"] == "open"
    assert api.post("admin1", f"/cases/{unanswered[0]['id']}/messages", {"body": "Not in scope for this site."}).status_code == 201
    mine = api.get("emp1", "/my/cases").json()["items"]
    assert mine[0]["latest_reply"] == "Not in scope for this site." and mine[0]["public_status"] == "in_progress"


@pytest.mark.live_integration
def test_history_search_rename_archive_are_private_to_the_owner(world):
    api = world
    c1 = api.ask("emp1", "how do I do goods receipt posting")["conversation_id"]
    c2 = api.ask("emp1", "start cycle counting")["conversation_id"]
    api.ask("emp2", "how do I do goods receipt posting")
    items = api.get("emp1", "/copilot/conversations").json()["items"]
    assert {i["id"] for i in items} == {c1, c2} and all(i["messages"] >= 2 for i in items)
    assert [i["id"] for i in api.get("emp1", "/copilot/conversations?q=cycle").json()["items"]] == [c2]
    patch = lambda user, cid, body: api.c.patch(f"/api/v1/copilot/conversations/{cid}", headers=headers(user), json=body)
    assert patch("emp1", c1, {"title": "My receiving question"}).status_code == 200
    assert api.get("emp1", "/copilot/conversations").json()["items"][0]["title"] in ("My receiving question", items[0]["title"])
    assert patch("emp2", c1, {"title": "hijack"}).status_code == 404                  # not yours
    assert patch("emp1", c1, {}).status_code == 422
    assert patch("emp1", c1, {"archived": True}).status_code == 200
    assert c1 not in {i["id"] for i in api.get("emp1", "/copilot/conversations").json()["items"]}
    assert [i["id"] for i in api.get("emp1", "/copilot/conversations?archived=true").json()["items"]] == [c1]
    assert patch("emp1", c1, {"archived": False}).status_code == 200
    assert c1 in {i["id"] for i in api.get("emp1", "/copilot/conversations").json()["items"]}
    assert api.get("emp_b", "/copilot/conversations").json()["items"] == []


@pytest.mark.live_integration
def test_self_service_resolution_counts_only_employee_confirmed_outcomes(world):
    api = world
    a = api.ask("emp1", "how do I do goods receipt posting")           # rated helpful -> confirmed
    api.post("emp1", "/copilot/feedback", {"message_id": a["message_id"], "rating": "helpful"})
    api.ask("emp1", "start cycle counting")                              # answered but never rated -> NOT counted
    c = api.ask("emp2", "how do I do goods receipt posting")            # helpful, then asks a person -> NOT counted
    api.post("emp2", "/copilot/feedback", {"message_id": c["message_id"], "rating": "helpful"})
    esc = api.post("emp2", "/copilot/escalate", {"conversation_id": c["conversation_id"], "note": "still stuck"})
    assert esc.status_code == 201, esc.text
    api.ask("emp2", "स्कैनर काम नहीं कर रहा")
    m = api.get("admin1", "/analytics/summary?days=30").json()["metrics"]
    assert m["conversations_total"] >= 3 and m["conversations_confirmed_resolved"] == 1
    assert m["self_service_resolution_pct"] == round(100 / m["conversations_total"], 1)
    assert m["answers_rated_helpful"] == 2 and m["answers_rated_not_helpful"] == 0
    assert m["cases_opened"] >= 1
    assert m["messages_in_devanagari"] == 1 and m["messages_in_latin_script"] == 3
    other = api.get("admin_b", "/analytics/summary").json()["metrics"]
    assert other["conversations_total"] == 0 and other["cases_opened"] == 0 and other["answers_rated_helpful"] == 0


@pytest.mark.live_integration
def test_howto_question_gets_the_approved_steps_not_a_bare_yes_or_no(world):
    api = world
    first = api.ask("emp1", "how do I do goods receipt posting")
    text = first["answer"]
    assert text.startswith("Here is the approved procedure for")
    assert "\n1. " in text and "\n2. " in text                      # real numbered steps from the published SOP
    assert "Say yes to start" in text                                # guided mode is offered, not forced
    started = api.ask("emp1", "yes", first["conversation_id"])
    assert started["active_session_id"] and started["active_step_number"] == 1
    assert api.ask("emp2", "what is the weather on mars")["answer"].startswith("I don't have an approved procedure")
