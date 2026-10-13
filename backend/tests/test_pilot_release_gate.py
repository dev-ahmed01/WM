"""Pilot release gate is deliberately NO_GO without inspected field evidence."""
import copy
import json
from pathlib import Path

from scripts.pilot_release_gate import (
    BOOLEAN_GATES, COUNTS, ZERO_GATES, assess_file, evaluate,
)

TEMPLATE = Path(__file__).resolve().parents[2] / "deploy" / "pilot" / "evidence.template.json"


def test_default_pilot_evidence_is_always_no_go():
    verdict = assess_file(TEMPLATE)
    assert verdict["decision"] == "NO_GO"
    assert "hosted_https_verified" in verdict["blocked_gates"]
    assert "field_audio_hindi_clips" in verdict["blocked_gates"]
    assert len(verdict["evidence_sha256"]) == 64


def test_release_gate_requires_every_field_and_rejects_boolean_counts():
    template = json.loads(TEMPLATE.read_text())
    evidence = copy.deepcopy(template)
    for key in BOOLEAN_GATES:
        evidence[key] = True
    for key, count in COUNTS.items():
        evidence[key] = count
    for key in ZERO_GATES:
        evidence[key] = 0
    for key in ("qa_quality_thresholds_approved","qa_thresholds_met",
                "voice_quality_thresholds_approved","voice_thresholds_met"):
        evidence[key] = True
    assert evaluate(evidence, "synthetic-only")["decision"] == "GO_FOR_LIMITED_PILOT"
    for key, value in (("hosted_restore_drill_passed",False),
                       ("invalid_citations",1),
                       ("field_audio_hinglish_clips",True),
                       ("qa_thresholds_met",False)):
        broken = dict(evidence, **{key:value})
        assert evaluate(broken, "synthetic-only")["decision"] == "NO_GO"
        assert key in evaluate(broken, "synthetic-only")["blocked_gates"]
