"""Evidence checklist for a limited warehouse pilot rollout.

This is not a substitute for independent human signoff: the input file must be
completed from inspected external evidence, never guessed from synthetic CI.
The CLI produces only gate names, counts and status, not document contents.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

BOOLEAN_GATES = (
    "hosted_https_verified", "runtime_database_role_verified",
    "hosted_restore_drill_passed", "cross_department_isolation_verified",
    "account_revocation_verified", "reference_archive_revocation_verified",
    "human_sop_approval_signed_off", "voice_review_before_send_verified",
    "pilot_rollback_verified", "independent_ai_review_signed_off",
    "security_review_signed_off",
)
# Required when the deployment exposes signed inbound and outbound WMS/ERP
# channels. These are external, independently inspected evidence claims only.
INTEGRATION_FIELD_GATES = (
    "integration_ingress_tls_verified",
    "integration_egress_firewall_verified",
    "integration_partner_ack_dedup_verified",
    "integration_secret_rotation_drilled",
    "integration_dead_letter_recovery_drilled",
    "integration_external_security_review_signed_off",
)

COUNTS = {
    "operator_pilot_days": 7,
    "distinct_pilot_operators": 3,
    "private_qa_cases": 120,
    "english_qa_cases": 30,
    "hindi_qa_cases": 30,
    "hinglish_qa_cases": 30,
    "independent_reviewers": 2,
    "field_audio_english_clips": 30,
    "field_audio_hindi_clips": 30,
    "field_audio_hinglish_clips": 30,
}
ZERO_GATES = (
    "cross_tenant_leaks", "invalid_citations", "unsafe_autonomous_step_advances",
    "unresolved_critical_pilot_incidents",
)


def evaluate(evidence: dict[str, Any], fingerprint: str) -> dict[str, Any]:
    if not isinstance(evidence, dict):
        raise ValueError("Pilot evidence must be an object")
    blocked: list[str] = []
    for key in BOOLEAN_GATES:
        if evidence.get(key) is not True:
            blocked.append(key)
    scope = evidence.get("bidirectional_integrations_in_scope")
    if not isinstance(scope,bool):
        blocked.append("bidirectional_integrations_in_scope")
    if scope is True:
        for key in INTEGRATION_FIELD_GATES:
            if evidence.get(key) is not True:
                blocked.append(key)
    for key, minimum in COUNTS.items():
        value = evidence.get(key)
        if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
            blocked.append(key)
    for key in ZERO_GATES:
        value = evidence.get(key)
        if isinstance(value, bool) or not isinstance(value, int) or value != 0:
            blocked.append(key)
    # Acceptance of accuracy requires a human-approved threshold and recorded
    # pass/fail, not synthetic benchmark numbers.
    for key in ("qa_quality_thresholds_approved", "qa_thresholds_met",
                "voice_quality_thresholds_approved", "voice_thresholds_met"):
        if evidence.get(key) is not True:
            blocked.append(key)
    return {
        "decision": "GO_FOR_LIMITED_PILOT" if not blocked else "NO_GO",
        "blocked_gates": blocked,
        "checked_gates": len(BOOLEAN_GATES) + len(COUNTS) + len(ZERO_GATES) + 5 + (len(INTEGRATION_FIELD_GATES) if scope is True else 0),
        "evidence_sha256": fingerprint,
        "notice": "Self-attested checklist only. An independent release owner must verify evidence and approve rollout.",
    }


def assess_file(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    if len(raw) > 65536:
        raise ValueError("Evidence checklist too large")
    return evaluate(json.loads(raw.decode("utf-8")), hashlib.sha256(raw).hexdigest())


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description="WorkMate limited pilot release gate")
    cli.add_argument("--evidence", type=Path, required=True)
    cli.add_argument("--strict", action="store_true")
    args = cli.parse_args()
    result = assess_file(args.evidence)
    print(json.dumps(result, indent=2))
    if args.strict and result["decision"] == "NO_GO":
        raise SystemExit(1)
