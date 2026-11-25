"""Render catalogue entries into OWD Markdown v1.1 accepted by the real compiler."""
from __future__ import annotations

import re
from typing import Dict, List

from demo.sop_catalog import AREAS, CATALOG, DEMO_DEPARTMENT_ID, HINGLISH, PROFILE, Sop

LABEL = "DEMONSTRATION SOP - original sample content for WorkMate Demo Logistics; not an approved company procedure"
_INV = {v: k for k, v in PROFILE.items()}
_PROFILE_NAMES = {
    "RECEIVING_ASSOCIATE": "Receiving Associate", "PICKER": "Picker", "PACKER": "Packer",
    "DISPATCH_ASSOCIATE": "Dispatch Associate", "INVENTORY_ASSOCIATE": "Inventory Associate",
    "QUALITY_INSPECTOR": "Quality Inspector", "MATERIAL_HANDLING": "Material Handling Worker",
    "RETURNS_ASSOCIATE": "Returns Associate", "MAINTENANCE_ASSOCIATE": "Maintenance Associate",
    "GENERAL_EMPLOYEE": "General Warehouse Employee",
}


def _clean(text: str) -> str:
    """Single-line, parser-safe text (no colons-at-start or markdown fences)."""
    return re.sub(r"\s+", " ", text.replace("{", "(").replace("}", ")").replace("`", "'")).strip()


def render(sop: Sop) -> str:
    dept_id = DEMO_DEPARTMENT_ID
    dept_name = AREAS[sop.area][1]
    roles = ", ".join(_PROFILE_NAMES[p] for p in sop.profiles) + ", Shift Supervisor"
    keywords = ", ".join(sop.keywords.split())
    synonyms = "; ".join(t.strip() for t in sop.terms.split(";") if t.strip())
    safety = sop.safety_critical
    n = len(sop.steps)
    out: List[str] = []
    w = out.append
    w("---")
    w('spec_version: "1.1"')
    w(f'sop_id: "{sop.code}"')
    w('version: "1.0.0"')
    w(f'department: "{dept_id}"')
    w('category: "OPERATIONAL_SOP"')
    w('owner: "Demo Operations Lead (fictional)"')
    w(f'priority: "{"HIGH" if safety else "MEDIUM"}"')
    w('difficulty: "BASIC"')
    w('estimated_duration: "10 mins"')
    w("roles_allowed:")
    for r in roles.split(", "):
        w(f'  - "{r}"')
    w('review_cycle: "ANNUAL"')
    w('effective_date: "2026-01-01"')
    w("---")
    w("")
    w("# 1 Document Metadata")
    w(f"sop_id: {sop.code}")
    w("version: 1.0.0")
    w(f"department: {dept_id}")
    w("category: OPERATIONAL_SOP")
    w("owner: Demo Operations Lead (fictional)")
    w(f"priority: {'HIGH' if safety else 'MEDIUM'}")
    w("difficulty: BASIC")
    w("estimated_duration: 10 mins")
    w(f"roles_allowed: {roles}")
    w("review_cycle: ANNUAL")
    w("effective_date: 2026-01-01")
    w("")
    w("# 2 AI Retrieval Metadata")
    w(f"keywords: {keywords}")
    w(f"synonyms: {synonyms}")
    hinglish = _clean(HINGLISH.get(sop.code, ""))
    w(f"search_phrases: {_clean(sop.title.lower())}, {_clean(sop.hindi_title)}" + (f", {hinglish}" if hinglish else ""))
    w(f"search_queries: how to {_clean(sop.title.lower())}")
    w(f"business_process: {dept_name} operations")
    w(f"workflow_tags: {AREAS[sop.area][0]}, demo{', safety_critical' if safety else ''}")
    w("")
    w("# 3 Workflow Definition")
    w(f"workflow_objective: {_clean(sop.purpose)}")
    w(f"business_goal: Consistent, safe execution of {_clean(sop.title.lower())}.")
    w(f"entry_conditions: Employee holds a job profile listed for this SOP and has been trained for the task.")
    w("exit_conditions: Procedure steps are completed or the exception is escalated.")
    w(f"expected_business_outcome: {_clean(sop.steps[-1][1])}.")
    w("")
    w("# 4 Workflow States & Steps")
    w("")
    for i, (instruction, outcome) in enumerate(sop.steps, start=1):
        key = f"STATE_STEP_{i}"
        initial = " is_initial=true" if i == 1 else ""
        w(f'::state[{key}]{{type="ATOMIC_STEP"{initial} purpose="{_clean(instruction)[:90]}" '
          f'responsible_role="{_PROFILE_NAMES[sop.profiles[0]]}"}}')
        w(f"## State {i}: Step {i}")
        w("")
        w(f":::step[STEP_{i}]")
        w(f"sequence_number: {i}")
        w(f"instruction: {_clean(instruction)}.")
        w(f"action: {_clean(instruction)}.")
        w(f"expected_outcome: {_clean(outcome)}.")
        if safety:
            w("safety_note: Stop and ask your supervisor if you are not trained or the situation is unsafe.")
        w(f"common_failure: {_clean(sop.exc_condition)}.")
        w(f"recovery_action: {_clean(sop.exc_action)}. Escalate to {sop.escalate_to}.")
        w("estimated_time: 2 mins")
        w("retry_policy: MAX_RETRIES_1")
        w(f"completion_criteria: {_clean(outcome)}.")
        w(":::")
        w("")
        if safety and i == 1:
            w(f":::rule[RULE_STOP_WORK]{{type=\"SAFETY_GUARDRAIL\" enforcement=\"HARD_STOP\"}}")
            w(f"If {_clean(sop.exc_condition).lower()}, stop work, keep people away and escalate to {sop.escalate_to}. "
              "Untrained employees must not attempt repairs, clean-up of hazardous material or any hazardous action.")
            w(":::")
            w("")
        if "photo" in (instruction + outcome).lower():
            w(f":::evidence[EVIDENCE_PHOTO_{i}]{{type=\"PHOTO_JPEG\" required=true}}")
            w("Attach the photo requested in this step.")
            w(":::")
            w("")
        nxt = f"STATE_STEP_{i + 1}" if i < n else "STATE_DECISION"
        w(f'::transition{{to="{nxt}" condition="ALWAYS"}}')
        w("")
    w('::state[STATE_DECISION]{type="DECISION" purpose="Check for the exception" '
      f'responsible_role="{_PROFILE_NAMES[sop.profiles[0]]}"}}')
    w("## Exception check")
    w("")
    w(":::decision[DEC_EXCEPTION]")
    w(f"question: Did the following happen - {_clean(sop.exc_condition)}?")
    w("alternative_path: STATE_END")
    w("options:")
    w("  - option_code: OPT_EXCEPTION")
    w("    option_label: Yes, this happened")
    w("    next_state: STATE_ESCALATE")
    w("  - option_code: OPT_NORMAL")
    w("    option_label: No, everything is normal")
    w("    next_state: STATE_END")
    w(":::")
    w("")
    w('::state[STATE_ESCALATE]{type="ESCALATION" purpose="Escalate the exception" is_terminal=false}')
    w("## Escalation")
    w("")
    w(":::step[STEP_ESCALATE]")
    w(f"sequence_number: {n + 1}")
    w(f"instruction: {_clean(sop.exc_action)}.")
    w(f"action: Escalate to {sop.escalate_to}.")
    w(f"expected_outcome: {sop.escalate_to} has been informed.")
    w("estimated_time: 5 mins")
    w("retry_policy: NO_RETRY")
    w(f"completion_criteria: {sop.escalate_to} has acknowledged.")
    w(":::")
    w("")
    w('::transition{to="STATE_END" condition="ALWAYS"}')
    w("")
    w('::state[STATE_END]{type="END" is_terminal=true purpose="Procedure complete"}')
    w("## Completed")
    w(f"{LABEL}.")
    w("")
    w("# 8 User Context")
    w(f"roles: {roles}")
    w("permissions: sop.read")
    w("experience_levels: BEGINNER, INTERMEDIATE")
    w("supported_languages: en-US, hi-IN")
    w(f"department: {dept_id}")
    w("")
    w("# 9 Analytics Events")
    w("events:")
    w("  - name: workflow_started")
    w("    trigger: EMPLOYEE_STARTED")
    w("    kpis: usage")
    w("  - name: workflow_completed")
    w("    trigger: EMPLOYEE_COMPLETED")
    w("    kpis: completion_rate")
    w("kpis: usage, completion_rate, escalation_rate")
    w("")
    w("# 10 Knowledge Relationships")
    w("parent_sop: None")
    w("related_sops: None")
    w("")
    w("# 11 References")
    w("primary_source: WorkMate Demo Logistics sample content (fictional)")
    w(f"supporting_sources: {LABEL}")
    w("compliance_standards: None claimed")
    return "\n".join(out) + "\n"


def all_documents() -> Dict[str, str]:
    return {s.code: render(s) for s in CATALOG}
