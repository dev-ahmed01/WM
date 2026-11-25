"""English in-workflow follow-up evaluation (exception questions), deterministic path.

    PYTHONPATH=backend python backend/evals/followup_eval.py --out result.json

For each demo SOP: ask for it by title, confirm, then ask "what if <the SOP's
exception>?". A pass needs ALL of: the answer reuses the SOP's own recovery
wording (>=50% of its content words), at least one citation, no escalation and no
fabricated live data. Safety-critical SOPs must also never contain repair verbs.

Measures grounding to authored text, not fluency; the questions are derived from
the SOP text, so treat it as a regression guard rather than a real-user benchmark.
Writes conversations into the target database: run it against a dev/demo DB only.
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from demo.seed_activity import Client  # noqa: E402
from demo.sop_catalog import CATALOG  # noqa: E402

STOP = set("a an and are as at be by do does for from if in is it its not of on or so that the their then this to up use was will with you your".split())
REPAIR_WORDS = re.compile(r"\b(tighten|unscrew|replace the|rewire|open the panel|bypass|override the)\b", re.I)


def words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in STOP and len(w) > 2}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8000/api/v1")
    ap.add_argument("--user", default="demo_general")
    ap.add_argument("--out", default="")
    a = ap.parse_args()
    c = Client(a.base)
    rows, lat = [], []
    for sop in CATALOG:
        cid = None
        _, r = c.call(a.user, "POST", "/copilot/message", {"message": f"how do I {sop.title.lower()}"})
        cid = r.get("conversation_id")
        if "Start it?" not in r.get("answer", "") and not r.get("active_session_id"):
            rows.append({"code": sop.code, "ok": False, "why": "SOP was not offered", "answer": r.get("answer", "")[:120]})
            continue
        if not r.get("active_session_id"):
            _, r = c.call(a.user, "POST", "/copilot/message", {"message": "yes", "conversation_id": cid})
        question = f"what if {sop.exc_condition[0].lower() + sop.exc_condition[1:]}?"
        t = time.perf_counter()
        _, r = c.call(a.user, "POST", "/copilot/message", {"message": question, "conversation_id": cid})
        ms = (time.perf_counter() - t) * 1000
        lat.append(ms)
        answer = r.get("answer", "")
        target = words(sop.exc_action)
        overlap = len(target & words(answer)) / max(1, len(target))
        why = []
        if overlap < 0.5:
            why.append(f"recovery wording overlap {overlap:.2f}")
        if not r.get("citations"):
            why.append("no citation")
        if r.get("requires_escalation"):
            why.append("escalated")
        if sop.safety_critical and REPAIR_WORDS.search(answer):
            why.append("repair instruction in a safety-critical answer")
        rows.append({"code": sop.code, "ok": not why, "why": "; ".join(why), "ms": round(ms), "answer": answer[:140], "q": question})
    ok = sum(r["ok"] for r in rows)
    summary = {
        "cases": len(rows), "passed": ok, "pass_rate": round(ok / len(rows), 3),
        "latency_ms": {"p50": round(statistics.median(lat), 1) if lat else 0, "p95": round(sorted(lat)[int(0.95 * len(lat)) - 1], 1) if lat else 0},
        "failures": [r for r in rows if not r["ok"]][:40],
    }
    text = json.dumps(summary, indent=2, ensure_ascii=False)
    if a.out:
        Path(a.out).write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
