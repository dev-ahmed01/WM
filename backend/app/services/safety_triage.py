"""Deterministic safety triage that runs BEFORE retrieval or any model call.

Hazard reports (fire, injury, chemical leak, electrical, failing equipment,
structural collapse) must never wait on, or be rephrased by, an LLM. This
module only recognises the situation and returns fixed stop-work wording. It
never produces repair, clean-up or first-aid instructions, and it never claims
an emergency service has been contacted.

False positives are acceptable (an extra safety reminder); false negatives are
not, so patterns are intentionally broad. English, Roman-script Hindi
(Hinglish) and Devanagari are covered. This is a safety *aid*; the site's
emergency alarm and number remain the authoritative channel.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

_I = re.IGNORECASE
_DEV = "ऀ-ॿ"


def _dev(*words: str) -> str:
    """Devanagari has no \b: require that the match is not inside a longer word (आग must not hit आगमन)."""
    return f"(?<![{_DEV}])(?:{'|'.join(words)})(?![{_DEV}])"


_RULES = (
    ("fire", re.compile(
        r"\b(fire|on fire|smoke|smoking|burning|flames?|aag|dhuan|dhuaan|jal\s*raha|jal\s*rahi)\b|" + _dev("आग", "धुआँ", "धुआं", r"जल\s*रहा"), _I)),
    ("injury", re.compile(
        r"\b(injur\w*|bleeding|blood|unconscious|fainted|collapsed|heart\s*attack|not\s*breathing|"
        r"chot|chhot|khoon|behosh|ghayal|zakhmi)\b|" + _dev("चोट", "खून", "बेहोश", "घायल"), _I)),
    ("chemical", re.compile(
        r"\b(chemical|toxic|fumes?|gas\s*leak|acid|zehr\w*|(?:box|drum|barrel|carton|container|pallet)\w*\s+(?:is\s+)?leak\w*|"
        r"leak\w*\s+(?:box|drum|barrel|carton|container|pallet)\w*)\b|" + _dev("रसायन", "केमिकल", r"गैस\s*लीक"), _I)),
    ("electrical", re.compile(
        r"\b(sparks?|sparking|electric\s*shock|electrocut\w*|short\s*circuit|exposed\s*wires?|"
        r"current\s*(?:laga|lag\s*gaya))\b|" + _dev("करंट", "चिंगारी"), _I)),
    ("equipment", re.compile(
        r"\b(forklift|fork\s*lift|reach\s*truck|pallet\s*jack|conveyor|belt|crane|lift)\b.{0,60}"
        r"\b(brake\w*|hydraulic|leak\w*|jam\w*|stuck|tilt\w*|tip\w*|not\s*stopping|steering|mast|"
        r"kharab|ruk\s*gaya|atak|fail\w*|broken|sparking)\b"
        r"|\b(brake\w*|hydraulic|steering|mast)\b.{0,40}\b(forklift|fork\s*lift|truck|conveyor)\b", _I)),
    ("structure", re.compile(
        r"\b(rack|racking|shelf|shelving|stack|pallet)s?\b.{0,40}"
        r"\b(collaps\w*|fall\w*|fell|tilt\w*|lean\w*|unstable|gir\s*(?:gaya|raha|gayi))\b", _I)),
    ("spill", re.compile(
        r"\b(spill\w*|slippery|oil\s+on\s+(?:the\s+)?floor|tel\s*gir\w*|paani\s*gir\w*|fisal\w*)\b|" + _dev(r"फैल\s*गया", "फिसल"), _I)),
)

# Pure how-to / training questions about safety topics are still answered by the
# SOP library; triage only fires on a reported situation or a fault.
_INFORMATIONAL = re.compile(
    r"^\s*(what\s+is|what\s+are|explain|define|tell\s+me\s+about)\b.*\b(policy|training|ppe|procedure|sop)\b", _I)

EN = (
    "SAFETY FIRST: stop work now and move yourself and anyone nearby away from the hazard. "
    "If someone is hurt, or there is fire, smoke, a chemical leak or an electrical hazard, "
    "use your site's emergency alarm or emergency number immediately. "
    "Do not repair, clean up or handle it yourself unless you are trained and authorised, "
    "and do not restart any equipment involved. Tell your supervisor now."
)
HI = (
    "पहले सुरक्षा: अभी काम रोकें और खुद को तथा आसपास के लोगों को खतरे से दूर करें। "
    "अगर कोई घायल है, या आग, धुआँ, केमिकल लीक या बिजली का खतरा है, तो तुरंत अपने साइट का "
    "इमरजेंसी अलार्म या इमरजेंसी नंबर इस्तेमाल करें। "
    "जब तक आप प्रशिक्षित और अधिकृत न हों, खुद मरम्मत, सफाई या हैंडलिंग न करें, "
    "और संबंधित उपकरण दोबारा चालू न करें। अभी अपने सुपरवाइज़र को बताएं।"
)

# Related reference SOPs a client library may map these to (codes are advisory).
HAZARD_SOPS = {
    "fire": "SOP-HSE-006", "injury": "SOP-HSE-005", "chemical": "SOP-HSE-007",
    "electrical": "SOP-EQP-006", "equipment": "SOP-EQP-004", "structure": "SOP-HSE-002",
    "spill": "SOP-HSE-007",
}


@dataclass(frozen=True)
class SafetyAlert:
    hazard: str
    related_sop: str

    def message(self, language: str | None, *, case_created: bool) -> str:
        follow = (
            "An urgent case has been created for your supervisor to see."
            if case_created else
            "I could not create a support case from here, so tell your supervisor directly."
        )
        follow_hi = (
            "आपके सुपरवाइज़र के लिए एक अर्जेंट केस बना दिया गया है।"
            if case_created else
            "मैं यहाँ से सपोर्ट केस नहीं बना पाया, इसलिए सुपरवाइज़र को सीधे बताएं।"
        )
        if language == "hi":
            return f"{HI} {follow_hi}"
        return f"{EN} {follow}\n\n{HI} {follow_hi}"


def detect(message: str) -> Optional[SafetyAlert]:
    text = (message or "").strip()
    if not text or _INFORMATIONAL.search(text):
        return None
    for hazard, pattern in _RULES:
        if pattern.search(text):
            return SafetyAlert(hazard, HAZARD_SOPS[hazard])
    return None
