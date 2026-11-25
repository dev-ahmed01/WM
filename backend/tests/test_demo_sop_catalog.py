"""Static gates for the 85-SOP demonstration library (no database needed)."""
from __future__ import annotations

from collections import Counter

import pytest

from app.compiler.pipeline import OWDCompilerPipeline
from demo.sop_catalog import CATALOG, DEMO_DEPARTMENT_ID, EXPECTED_PER_AREA
from demo.sop_generator import LABEL, render


def test_distribution_matches_brief():
    assert len(CATALOG) == 85
    assert dict(Counter(s.area for s in CATALOG)) == EXPECTED_PER_AREA


def test_every_sop_has_required_content():
    for s in CATALOG:
        assert s.code.startswith("SOP-") and s.title and s.hindi_title and s.purpose
        assert len(s.steps) >= 2, s.code
        assert s.exc_condition and s.exc_action and s.escalate_to, s.code
        assert any("ऀ" <= ch <= "ॿ" for ch in s.hindi_title), s.code
        assert s.terms, f"{s.code} lacks English=Hindi terminology"
        assert ":" not in s.exc_condition, f"{s.code}: colon breaks OWD key parsing"


@pytest.mark.parametrize("sop", CATALOG, ids=lambda s: s.code)
def test_sop_compiles_with_a_reachable_graph(sop):
    report = OWDCompilerPipeline.process_owd(
        render(sop), department_id=DEMO_DEPARTMENT_ID, title=sop.title, skip_loader=True)
    assert report["compilation_status"] == "SUCCESS", report["validation_errors"]
    assert report["number_of_decisions"] == 1
    assert not [w for w in report["warnings"] if "Unreachable" in w], report["warnings"]


def test_safety_critical_sops_stop_work_and_forbid_untrained_action():
    safety = [s for s in CATALOG if s.safety_critical]
    assert len(safety) >= 15
    for s in safety:
        md = render(s)
        assert 'enforcement="HARD_STOP"' in md, s.code
        assert "Untrained employees must not" in md, s.code
        report = OWDCompilerPipeline.process_owd(
            md, department_id=DEMO_DEPARTMENT_ID, title=s.title, skip_loader=True)
        assert report["number_of_safety_rules"] >= 1, s.code


def test_every_sop_is_labelled_as_demonstration():
    for s in CATALOG:
        assert LABEL in render(s), s.code


def test_evidence_types_match_database_constraint():
    import re
    allowed = {"DOCUMENT_PDF", "PHOTO_JPEG", "DIGITAL_SIGNATURE", "CHECKSUM_HASH", "SUPERVISOR_APPROVAL"}
    for s in CATALOG:
        for found in re.findall(r':::evidence\[[^\]]+\]\{type="([A-Z_]+)"', render(s)):
            assert found in allowed, (s.code, found)
