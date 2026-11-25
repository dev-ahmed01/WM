"""Honest handling of questions that need live warehouse data.

WorkMate has no connected WMS/ERP feed by default. A question such as "stock level
of SKU 123" must say the data is unavailable, never produce a number or a
procedure-flavoured guess.
"""
from __future__ import annotations

import re

_PATTERN = re.compile(
    r"\b(stock|inventory|quantity|qty)\s+(level|balance|available|on\s*hand)\b"
    r"|\bhow\s+many\s+(units|pieces|cartons|boxes|pallets)\b.{0,40}\b(in|at|left|available)\b"
    r"|\b(status|location|where)\b.{0,20}\b(of|is|for)\b.{0,25}\b(shipment|order|asn|po|pallet|sku|bin|consignment)\b"
    r"|\bsku\s*[-#]?\s*\w*\d\w*\b.{0,30}\b(bin|stock|location|quantity)\b"
    r"|\b(bin|location)\s+[a-z]-?\d+", re.IGNORECASE)

MESSAGE = ("I can't see live warehouse data (stock levels, bin locations or shipment status) from here, "
           "so I won't guess a number. Check the WMS, or ask your supervisor or inventory team.")


def needs_live_data(message: str) -> bool:
    return bool(_PATTERN.search(message or ""))
