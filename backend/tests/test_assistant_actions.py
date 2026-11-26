import pytest
from app.services import assistant_actions as a


@pytest.mark.parametrize("msg,kind,qty", [
    ("Sir, shipment mein do boxes missing hain", "shortage", 2),
    ("2 cartons damaged in the delivery", "damage", 2),
    ("three boxes short in this truck", "shortage", 3),
    ("teen dabbe kam aaye truck mein", "shortage", 3),
    ("shipment short", "shortage", None),
    ("what should I do, 5 boxes are missing from the delivery", "shortage", 5),
])
def test_reports_are_detected(msg, kind, qty):
    found = a.detect(msg)
    assert found and (found.kind, found.quantity) == (kind, qty)


@pytest.mark.parametrize("msg", [
    "how do I handle damaged inbound goods",
    "what is the process for a shipment shortage",
    "where should I report missing stock",
    "I found a damaged box",
    "scanner missing",
    "do I need to count the delivery",
])
def test_how_to_questions_are_not_reports(msg):
    assert a.detect(msg) is None, msg


def test_state_round_trip_and_garbage_is_ignored():
    assert a.parse_state(a.intent_confirm("shortage", 2)) == ("confirm", "shortage", 2)
    assert a.parse_state(a.intent_ask("damage")) == ("ask", "damage", None)
    for junk in (None, "", "ACTION_CONFIRM:shortage:x", "ACTION_CONFIRM:bogus:2", "WORKFLOW_START_CONFIRMED"):
        assert a.parse_state(junk) is None


def test_proposal_states_what_it_does_not_do():
    text = a.proposal("shortage", 1)
    assert "1 box." in text.replace("box,", "box.") or "1 box" in text
    assert "does not adjust stock" in text and "Reply yes" in text
