"""Unit tests for the modular OWD Compiler subsystem (Parser, Validator, Compiler, Loader, Pipeline)."""

import unittest
from unittest.mock import MagicMock, patch

from app.compiler.models import OWDDocument, ValidationReport, CompiledWorkflow, LoadResult
from app.compiler.parser import OWDParser
from app.compiler.validator import OWDValidator
from app.compiler.compiler import OWDCompiler
from app.compiler.loader import OWDLoader
from app.compiler.pipeline import OWDCompilerPipeline
from app.compiler.exceptions import OWDValidationException


SAMPLE_OWD_MARKDOWN = """# SOP-FIN-001: Expense Authorization Procedure

::state[STATE_INIT]{type="ATOMIC_STEP" is_initial=true}
## Verify Receipt Information
Confirm that uploaded receipt contains clear merchant name and date.

- [ ] Check merchant name ::step[STEP_MERCHANT_NAME]
- [ ] Verify transaction date is within 30 days ::step[STEP_DATE_CHECK]

:::rule[RULE_VAL_01]{type="SAFETY_GUARDRAIL" enforcement="HARD_STOP"}
Expenses over $5,000 require manager pre-approval.
:::

:::evidence[EVIDENCE_RECEIPT_PDF]{type="DOCUMENT_PDF" required=true}
Must attach original PDF receipt.
:::

::transition{to="STATE_APPROVAL" condition="ALWAYS"}

::state[STATE_APPROVAL]{type="DECISION"}
## Approval Decision
Select appropriate sign-off route.
::transition{to="STATE_END" condition="ALWAYS"}

::state[STATE_END]{type="END" is_terminal=true}
## Workflow Completed
Expense verification complete.
"""


class TestOWDCompilerSubsystem(unittest.TestCase):
    """Test suite for independent modular compiler stages."""

    def test_parser_module(self):
        """Tests that OWDParser converts raw markdown into OWDDocument AST graph."""
        doc = OWDParser.parse(
            markdown_text=SAMPLE_OWD_MARKDOWN,
            workflow_code="SOP-FIN-001",
            title="Expense Authorization Procedure",
            department_id="dept_finance",
        )

        self.assertIsInstance(doc, OWDDocument)
        self.assertEqual(doc.workflow.workflow_code, "SOP_FIN_001")
        self.assertEqual(doc.workflow.department_id, "dept_finance")
        self.assertEqual(len(doc.workflow.states), 3)

        initial_state = doc.workflow.states[0]
        self.assertEqual(initial_state.state_key, "STATE_INIT")
        self.assertEqual(len(initial_state.steps), 2)
        self.assertEqual(len(initial_state.safety_rules), 1)
        self.assertEqual(len(initial_state.evidence_specs), 1)

    def test_validator_module_valid_doc(self):
        """Tests that OWDValidator returns valid report for valid OWD AST graph."""
        doc = OWDParser.parse(SAMPLE_OWD_MARKDOWN, workflow_code="SOP-FIN-001")
        report = OWDValidator.validate(doc)

        self.assertIsInstance(report, ValidationReport)
        self.assertTrue(report.is_valid)
        self.assertEqual(len(report.errors), 0)
        self.assertEqual(report.states_count, 3)
        self.assertEqual(report.steps_count, 2)
        self.assertEqual(report.safety_rules_count, 1)

    def test_validator_module_broken_transition(self):
        """Tests that OWDValidator flags broken transition targets as validation errors."""
        broken_markdown = """::state[STATE_INIT]{is_initial=true}
- [ ] Step 1
::transition{to="NON_EXISTENT_STATE" condition="ALWAYS"}
"""
        doc = OWDParser.parse(broken_markdown, workflow_code="SOP-BROKEN")
        report = OWDValidator.validate(doc)

        self.assertFalse(report.is_valid)
        self.assertGreaterEqual(len(report.errors), 1)
        self.assertTrue(any("NON_EXISTENT_STATE" in err for err in report.errors))

    def test_compiler_module(self):
        """Tests that OWDCompiler transforms OWDDocument AST into database-ready CompiledWorkflow object."""
        doc = OWDParser.parse(SAMPLE_OWD_MARKDOWN, workflow_code="SOP-FIN-001")
        compiled = OWDCompiler.compile(doc, stage_file_uri="@RAW_OWD_STAGE/sop_fin_001.md")

        self.assertIsInstance(compiled, CompiledWorkflow)
        self.assertIn("id", compiled.workflow_payload)
        self.assertEqual(compiled.workflow_payload["workflow_code"], "SOP_FIN_001")

        self.assertEqual(len(compiled.states_payload), 3)
        self.assertEqual(len(compiled.steps_payload), 2)
        self.assertEqual(len(compiled.rules_payload), 1)
        self.assertEqual(len(compiled.search_metadata_payload), 3)

    @patch("app.compiler.loader.get_snowflake_connection")
    def test_loader_module(self, mock_get_conn):
        """Tests that OWDLoader executes database MERGE queries."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.__enter__.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_get_conn.return_value = mock_conn

        doc = OWDParser.parse(SAMPLE_OWD_MARKDOWN, workflow_code="SOP-FIN-001")
        compiled = OWDCompiler.compile(doc)
        mock_cursor.fetchone.return_value = (
            "published",
            len(compiled.states_payload),
            len(compiled.search_metadata_payload),
        )
        res = OWDLoader.load(compiled)

        self.assertIsInstance(res, LoadResult)
        self.assertTrue(res.success)
        self.assertGreaterEqual(len(res.tables_updated), 3)
        self.assertTrue(mock_cursor.execute.called)
        statements = [str(call.args[0]).strip().upper() for call in mock_cursor.execute.call_args_list]
        self.assertEqual(statements[0], "BEGIN")
        self.assertEqual(statements[-1], "COMMIT")
        self.assertTrue(any("SET STATUS = 'DEPRECATED'" in statement for statement in statements))
        self.assertTrue(any("SET STATUS = 'ARCHIVED'" in statement for statement in statements))

    def test_pipeline_end_to_end(self):
        """Tests end-to-end OWDCompilerPipeline execution and report generation."""
        report = OWDCompilerPipeline.process_owd(
            markdown_text=SAMPLE_OWD_MARKDOWN,
            workflow_code="SOP-FIN-001",
            title="Expense Authorization",
            department_id="dept_finance",
            skip_loader=True,
        )

        self.assertEqual(report["compilation_status"], "SUCCESS")
        self.assertEqual(report["deployment_status"], "STAGED")
        self.assertEqual(report["number_of_states"], 3)
        self.assertEqual(report["number_of_steps"], 2)
        self.assertEqual(report["number_of_safety_rules"], 1)


if __name__ == "__main__":
    unittest.main()
