import pytest
from app.services.live_data_guard import MESSAGE, needs_live_data


@pytest.mark.parametrize("q", [
    "What is the stock level of SKU 12345 in bin A-01?",
    "where is shipment PO4455",
    "how many cartons left in aisle 4",
    "status of order 8891",
])
def test_live_data_questions_detected(q):
    assert needs_live_data(q), q


@pytest.mark.parametrize("q", [
    "How do I do a cycle count?", "Galat item pick ho gaya", "Where should I report missing stock?",
    "What is the process for requesting leave?", "scanner kaam nahi kar raha hai",
])
def test_procedural_questions_pass_through(q):
    assert not needs_live_data(q), q


def test_message_makes_no_numeric_claim():
    assert not any(ch.isdigit() for ch in MESSAGE)


@pytest.mark.parametrize("q", ["how do I physical stock count", "how to do cycle count", "inventory count SOP"])
def test_count_procedures_are_not_live_data(q):
    assert not needs_live_data(q), q
