"""Deterministic safety triage: recall on hazards, silence on ordinary questions."""
import pytest

from app.services import safety_triage as st

HAZARDS = [
    ("there is smoke coming from the packing area", "fire"),
    ("aag lag gayi hai", "fire"),
    ("गोदाम में आग लग गई", "fire"),
    ("a worker is bleeding and unconscious", "injury"),
    ("kisi ko chot lag gayi", "injury"),
    ("a chemical box is leaking should I clean it up", "chemical"),
    ("conveyor belt is jammed and sparking can I open the panel", "electrical"),
    ("hydraulic leak on forklift how do I fix it myself", "equipment"),
    ("forklift ka brake kharab hai", "equipment"),
    ("the rack is leaning and pallets are falling", "structure"),
    ("oil on the floor near dock 3", "spill"),
]
ORDINARY = [
    "How do I receive this shipment?",
    "scanner kaam nahi kar raha hai",
    "What is the process for requesting leave?",
    "Galat item pick ho gaya, ab kya karun?",
    "सामान कम आया है, क्या करूँ?",
    "what is the PPE policy",
    "printer print nahi kar raha",
]


@pytest.mark.parametrize("text,hazard", HAZARDS)
def test_hazard_reports_are_detected(text, hazard):
    alert = st.detect(text)
    assert alert is not None, text
    assert alert.hazard == hazard, (text, alert.hazard)


@pytest.mark.parametrize("text", ORDINARY)
def test_ordinary_questions_are_not_alarmed(text):
    assert st.detect(text) is None, text


def test_message_never_gives_repair_or_firstaid_steps_or_claims_contact():
    for lang in ("en", "hi"):
        for created in (True, False):
            msg = st.detect("fire").message(lang, case_created=created).lower()
            for forbidden in ("tighten", "replace the", "open the panel", "apply pressure", "i have called", "ambulance is on"):
                assert forbidden not in msg
    assert "emergency" in st.EN.lower() and "do not repair" in st.EN.lower()


def test_case_status_is_reported_honestly():
    ok = st.detect("fire").message("en", case_created=True)
    bad = st.detect("fire").message("en", case_created=False)
    assert "urgent case has been created" in ok
    assert "could not create a support case" in bad


def test_devanagari_words_do_not_match_inside_longer_words():
    # "आगमन" (arrival) contains "आग" (fire) but is not a hazard.
    assert st.detect("सप्लायर आगमन और गेट जाँच") is None
    assert st.detect("आग लग गई") is not None
