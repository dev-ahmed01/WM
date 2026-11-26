"""Typed, allowlisted assistant actions (currently: shipment discrepancy report).

The model never executes anything. A recognised situation produces a *proposal*
the employee must confirm in plain words; only then is the existing, validated
handover record written (server-side authorisation, one record per confirmation).
The reply states exactly what was and was not done: reporting never adjusts
stock, contacts a supplier or closes a purchase order.

Understands English and Roman-script Hindi ("Sir, shipment mein do boxes missing hain").
State lives in the intent of the assistant's previous message (no new table):
    ACTION_ASK:<kind>            waiting for a quantity
    ACTION_CONFIRM:<kind>:<qty>  waiting for yes / no
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

_NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "ek": 1, "do": 2, "teen": 3, "char": 4, "chaar": 4, "paanch": 5, "panch": 5, "chhe": 6, "chhah": 6,
    "saat": 7, "aath": 8, "nau": 9, "das": 10,
}
_UNITS = r"(?:boxes|box|cartons?|carton|pallets?|pallet|packets?|packet|cases?|case|pieces?|piece|units?|unit|items?|dabbe|dibbe|dabba|bori|bags?|bag)"
_NUMBER = re.compile(rf"\b(\d{{1,4}}|{'|'.join(_NUMBER_WORDS)})\s+{_UNITS}\b", re.I)
_BARE_NUMBER = re.compile(r"^\W*(\d{1,4}|" + "|".join(_NUMBER_WORDS) + r")\W*(?:" + _UNITS + r")?\W*$", re.I)

_CONTEXT = re.compile(r"\b(shipment|delivery|truck|trailer|consignment|inbound|supplier|po|asn|grn|delivery note|challan|maal|container)\b", re.I)
_SHORT = re.compile(r"\b(missing|short(?:age)?|not received|didn'?t (?:arrive|come)|less|kam|kam aaya|kam hain|kam hai|ghayab|gum|nahi aaye|nahin aaye)\b", re.I)
_DAMAGE = re.compile(r"\b(damaged|damage|broken|crushed|torn|wet|toot(?:a|e|i)?|tuta|tute|kharab|phat(?:a|e)?)\b", re.I)
_EXCESS = re.compile(r"\b(extra|excess|over(?:age)?|zyada|jyada|more than)\b", re.I)

LABEL = {"shortage": "shortage", "damage": "damaged goods", "excess": "excess"}
EXCEPTION = {"shortage": "quantity_mismatch", "excess": "quantity_mismatch", "damage": "damage"}
SEVERITY = {"shortage": "normal", "excess": "normal", "damage": "high"}


# "How do I handle damaged goods?" is a request for a procedure, not a report of a shortage.
_QUESTION_START = re.compile(r"^\W*(?:how|what|where|when|why|which|who|can|could|should)\b|^\W*(?:do|does)\s+(?:i|we|you)\b", re.I)


@dataclass(frozen=True)
class Discrepancy:
    kind: str
    quantity: Optional[int]


def _to_int(token: str) -> int:
    t = token.lower()
    return int(t) if t.isdigit() else _NUMBER_WORDS[t]


def parse_quantity(message: str) -> Optional[int]:
    m = _NUMBER.search(message or "") or _BARE_NUMBER.match(message or "")
    if not m:
        return None
    value = _to_int(m.group(1))
    return value if 1 <= value <= 9999 else None


def detect(message: str) -> Optional[Discrepancy]:
    """A shipment-level discrepancy: a kind word AND (a quantity or shipment context)."""
    text = message or ""
    kind = ("damage" if _DAMAGE.search(text) else "shortage" if _SHORT.search(text)
            else "excess" if _EXCESS.search(text) else None)
    if kind is None:
        return None
    quantity = parse_quantity(text)
    if quantity is None and (not _CONTEXT.search(text) or _QUESTION_START.search(text)):
        return None
    return Discrepancy(kind, quantity)


def ask_for_quantity(kind: str) -> str:
    return (f"I can report this {LABEL[kind]} to your supervisor. How many boxes or cartons are affected? "
            "Reply with a number, or say no to cancel.")


def proposal(kind: str, quantity: int) -> str:
    return (f"I can report this to your shift supervisor: shipment {LABEL[kind]}, {quantity} "
            f"box{'es' if quantity != 1 else ''}. This only sends a report. It does not adjust stock, contact the supplier "
            "or close the purchase order. Reply yes to send it, or no to cancel.")


def intent_ask(kind: str) -> str:
    return f"ACTION_ASK:{kind}"


def intent_confirm(kind: str, quantity: int) -> str:
    return f"ACTION_CONFIRM:{kind}:{quantity}"


def parse_state(intent: Optional[str]) -> Optional[tuple[str, str, Optional[int]]]:
    """('ask'|'confirm', kind, quantity) from the previous assistant intent, else None."""
    parts = (intent or "").split(":")
    if parts[0] == "ACTION_ASK" and len(parts) == 2 and parts[1] in LABEL:
        return "ask", parts[1], None
    if parts[0] == "ACTION_CONFIRM" and len(parts) == 3 and parts[1] in LABEL and parts[2].isdigit():
        return "confirm", parts[1], int(parts[2])
    return None


def handover_fields(kind: str, quantity: int, original_message: str) -> dict:
    noun = f"{quantity} box{'es' if quantity != 1 else ''}"
    return {
        "recipient": "Shift supervisor",
        "disposition": "blocked_supervisor",
        "exception_type": EXCEPTION[kind],
        "severity": SEVERITY[kind],
        "next_action": f"Review shipment {LABEL[kind]}: {noun} reported. Check against the delivery paperwork and decide next steps.",
        "notes": f"Reported through WorkMate Copilot. Employee said: {original_message.strip()[:400]}",
    }
