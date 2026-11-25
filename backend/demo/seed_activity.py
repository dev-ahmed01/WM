"""Seed demo work, conversations and a handover THROUGH THE REAL HTTP API.

    # backend running on :8000 with demo users seeded (python -m demo.seed_demo)
    PYTHONPATH=backend python -m demo.seed_activity [--base http://127.0.0.1:8000/api/v1]

Everything is created as the demo users with their real roles, so each record
passes the same validation, scoping and audit path as production use. Safe to
re-run: work items are keyed by an external reference ("DEMO-..."), and the
conversation/handover seeding is skipped once the demo employee has history.
Nothing here pretends a connected WMS exists; references are labelled demo.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

CREDS = Path(__file__).resolve().parents[2] / ".demo-credentials.local.json"

WORK = (
    ("demo_receiving", "Receive inbound trailer from Acme Supplies (demo)", "receiving", "high", "DEMO-WI-001",
     "Verify seal and PO, count cartons, report any shortage or damage."),
    ("demo_receiving", "Putaway received pallets to rack zone B (demo)", "putaway", "standard", "DEMO-WI-002",
     "Use the allocated locations and confirm each scan."),
    ("demo_picker", "Pick wave 14 - 22 order lines (demo)", "picking", "standard", "DEMO-WI-003",
     "Follow the pick list sequence and report short picks."),
    ("demo_inventory", "Cycle count aisle 7 (demo)", "stock_count", "standard", "DEMO-WI-004",
     "Blind count; recount differences before reporting."),
    ("demo_dispatch", "Dispatch manifest for carrier route R3 (demo)", "dispatch", "high", "DEMO-WI-005",
     "Verify package count against the manifest before carrier handover."),
)

# work reference -> SOP the manager binds it to (so employees can run it step by step)
BIND = {"DEMO-WI-001": "SOP_INB_005", "DEMO-WI-002": "SOP_STO_001", "DEMO-WI-003": "SOP_PCK_001",
        "DEMO-WI-004": "SOP_INV_001", "DEMO-WI-005": "SOP_OUT_002"}

# (employee, question, optional follow-up replies sent in the same conversation)
CONVERSATIONS = (
    ("demo_picker", "Galat item pick ho gaya, ab kya karun?", ()),
    ("demo_receiving", "how do I do goods receipt posting", ("yes", "done")),
    ("demo_packer", "which box should I use for a fragile item", ()),
    ("demo_mhe", "hydraulic leak on forklift how do I fix it myself", ()),
    ("demo_general", "what is the policy for bonus payments", ()),
    ("demo_inventory", "What is the stock level of SKU 12345 in bin A-01?", ()),
)


class Client:
    def __init__(self, base: str):
        self.base = base.rstrip("/")
        self.creds = json.loads(CREDS.read_text())
        self.tokens: dict[str, str] = {}

    def call(self, user: str, method: str, path: str, body=None):
        if user not in self.tokens:
            c = self.creds[user]
            _, t = self._raw("POST", "/auth/login", {"email": c["email"], "password": c["password"]}, None)
            self.tokens[user] = t["access_token"]
        return self._raw(method, path, body, self.tokens[user])

    def _raw(self, method, path, body, token):
        req = urllib.request.Request(
            self.base + path, method=method, data=None if body is None else json.dumps(body).encode(),
            headers={"Content-Type": "application/json", **({"Authorization": "Bearer " + token} if token else {})})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.status, json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"{}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8000/api/v1")
    c = Client(ap.parse_args().base)
    summary = {"work_created": 0, "work_existing": 0, "conversations": 0, "handovers": 0, "errors": []}

    status, existing = c.call("demo_manager_hyd", "GET", "/work/items?limit=100")
    have = {i.get("external_reference") for i in (existing.get("items") if isinstance(existing, dict) else existing) or []}
    for emp, title, wtype, prio, ref, instr in WORK:
        if ref in have:
            summary["work_existing"] += 1
            continue
        status, body = c.call("demo_manager_hyd", "POST", "/work/items", {
            "title": title, "work_type": wtype, "priority": prio, "instructions": instr,
            "external_reference": ref, "assigned_to": emp})
        if status == 201:
            summary["work_created"] += 1
        else:
            summary["errors"].append((ref, status, body))

    _, procs = c.call("demo_manager_hyd", "GET", "/work/execution/procedures")
    version_of = {p["workflow_code"]: p["workflow_version_id"] for p in procs.get("items", [])}
    _, items = c.call("demo_manager_hyd", "GET", "/work/items?limit=100")
    summary["bound"] = 0
    for item in items.get("items", []):
        code = BIND.get(item.get("external_reference"))
        if code and code in version_of and not item.get("workflow_version_id"):
            status, body = c.call("demo_manager_hyd", "POST", f"/work/execution/{item['id']}/bind",
                                  {"workflow_version_id": version_of[code]})
            if status == 200:
                summary["bound"] += 1
            else:
                summary["errors"].append(("bind " + item["external_reference"], status, body))

    _, hist = c.call("demo_picker", "GET", "/copilot/history")
    if not hist.get("sessions"):
        last_conv = {}
        for emp, question, followups in CONVERSATIONS:
            status, r = c.call(emp, "POST", "/copilot/message", {"message": question})
            if status != 200:
                summary["errors"].append((question, status, r))
                continue
            conv = r.get("conversation_id")
            for reply in followups:
                c.call(emp, "POST", "/copilot/message", {"message": reply, "conversation_id": conv})
            last_conv[emp] = conv
            summary["conversations"] += 1
    _, ho = c.call("demo_manager_hyd", "GET", "/handover")
    if not (ho if isinstance(ho, list) else ho.get("items", [])):
        _, rcv = c.call("demo_receiving", "GET", "/copilot/history")
        convs = rcv.get("sessions", [])
        conv = convs[0]["id"] if convs else None
        if conv:
            status, body = c.call("demo_receiving", "POST", "/handover", {
                "conversation_id": conv, "recipient_label": "Next shift receiving lead",
                "disposition": "pending_next_shift", "exception_type": "quantity_mismatch", "severity": "high",
                "next_action": "Follow up with supplier on two missing cartons from the inbound trailer (demo).",
                "notes": "Demo handover created by seed_activity."})
            if status == 201:
                summary["handovers"] += 1
            else:
                summary["errors"].append(("handover", status, body))
    print(json.dumps(summary, indent=2, default=str))
    return 1 if summary["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
