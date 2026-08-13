"""Compatibility tests for the JSON-block and Markdown-table OWD dialect."""

from pathlib import Path

from app.compiler.compiler import OWDCompiler
from app.compiler.parser import OWDParser
from app.compiler.validator import OWDValidator


FIXTURE = Path(
    "backend/tests/fixtures/owd_repository/inbound/receive_shipment_json_table.md"
)


def test_json_table_format_builds_valid_executable_graph():
    document = OWDParser.parse(
        markdown_text=FIXTURE.read_text(encoding="utf-8"),
        title="Receive Shipment",
        department_id="dept_inbound",
    )
    report = OWDValidator.validate(document)

    assert report.is_valid, report.errors
    assert document.workflow.workflow_code == "WH_REC_001"
    assert document.workflow.department_id == "dept_inbound"
    assert [state.state_key for state in document.workflow.states] == [
        "STATE_S1",
        "STATE_S2",
        "STATE_S3",
        "STATE_S4",
    ]
    assert [state.is_initial for state in document.workflow.states] == [
        True,
        False,
        False,
        False,
    ]
    assert document.workflow.states[-1].is_terminal is True
    decision = document.workflow.states[1].decisions[0]
    assert [option.target_state_key for option in decision.options] == [
        "STATE_S4",
        "STATE_S3",
    ]
    assert [event.event_name for event in document.analytics.events] == [
        "workflow_started",
        "workflow_completed",
    ]
    assert document.analytics.kpis == ["Receipt cycle time", "discrepancy rate"]
    relationship_types = {
        relationship.relationship_type for relationship in document.relationships
    }
    assert {"PREVIOUS_SOP", "NEXT_SOP", "ESCALATION_SOP"} <= relationship_types


def test_json_table_format_compiles_without_losing_steps_or_decisions():
    document = OWDParser.parse(
        markdown_text=FIXTURE.read_text(encoding="utf-8"),
        title="Receive Shipment",
        department_id="dept_inbound",
    )

    compiled = OWDCompiler.compile(
        document,
        stage_file_uri="@RAW_OWD_STAGE/WH_REC_001/v1/source.md",
    )

    assert len(compiled.states_payload) == 4
    assert len(compiled.steps_payload) == 4
    assert len(compiled.decisions_payload) == 1
    assert len(compiled.decision_options_payload) == 2
    assert len(compiled.transitions_payload) == 4


def test_existing_directive_format_remains_supported():
    existing = Path(
        "backend/tests/fixtures/owd_repository/inbound/receive_shipment_v1_1.md"
    )
    document = OWDParser.parse(
        markdown_text=existing.read_text(encoding="utf-8"),
        department_id="dept_inbound",
    )

    assert OWDValidator.validate(document).is_valid
    assert len(document.workflow.states) == 6
