"""Offline labeled QA smoke metrics are not production evidence."""
from evals.reference_quality_smoke import run_fixture


def test_reference_quality_smoke():
    report = run_fixture()
    assert report['questions'] >= 14
    assert report['lexical_top1_accuracy'] >= 0.75, report
    assert report['lexical_recall_at_3'] >= 0.90, report
    assert report['correct_abstention_rate'] == 1.0, report
    assert report['citation_span_integrity'] == 1.0, report
    assert not report['failures'], report
