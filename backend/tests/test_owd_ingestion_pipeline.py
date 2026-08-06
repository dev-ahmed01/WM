"""Automated Test Suite for OWD Ingestion Pipeline.

Tests single workflow loading, directory recursive discovery, duplicate SHA256 hash detection,
version number incrementing, validation error isolation, Snowflake transaction rollback handling,
and deployment report generation.
"""

import os
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from scripts.load_owd import (
    discover_markdown_files,
    process_single_owd,
    run_ingestion_pipeline,
    derive_department_from_path,
    write_report_files,
)
from app.compiler.utils import calculate_source_hash
from app.compiler.exceptions import OWDLoaderException


VALID_OWD_MARKDOWN = """# SOP-TEST-001: Test Receiving SOP

::state[STATE_INIT]{type="ATOMIC_STEP" is_initial=true}
# Step 1: Initial Check
Verify package barcode label.

- [ ] Check barcode label ::step[STEP_CHECK_BARCODE]

:::rule[RULE_SAFETY_01]{type="SAFETY_GUARDRAIL" enforcement="HARD_STOP"}
Package must not be opened if seal is broken.
:::

::transition{to="STATE_END" condition="ALWAYS"}

::state[STATE_END]{type="END" is_terminal=true}
# Step 2: Completion
Process complete.
"""

INVALID_OWD_MARKDOWN = """::state[STATE_INIT]{is_initial=true}
- [ ] Invalid step
::transition{to="NON_EXISTENT_STATE_KEY" condition="ALWAYS"}
"""


class TestOWDIngestionPipeline(unittest.TestCase):
    """Test suite for the production-grade OWD Ingestion Pipeline."""

    def setUp(self):
        """Sets up a temporary directory environment for test markdown files and reports."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.test_root = Path(self.temp_dir.name)

        # Create mock repository subdirectories
        self.inbound_dir = self.test_root / "inbound"
        self.templates_dir = self.test_root / "templates"
        self.inbound_dir.mkdir(parents=True)
        self.templates_dir.mkdir(parents=True)

        self.valid_file = self.inbound_dir / "receive_test.md"
        self.valid_file.write_text(VALID_OWD_MARKDOWN, encoding="utf-8")

        self.invalid_file = self.inbound_dir / "broken_test.md"
        self.invalid_file.write_text(INVALID_OWD_MARKDOWN, encoding="utf-8")

        self.template_file = self.templates_dir / "template_test.md"
        self.template_file.write_text(VALID_OWD_MARKDOWN, encoding="utf-8")

        self.logger_mock = MagicMock()

    def tearDown(self):
        """Cleans up temporary files."""
        self.temp_dir.cleanup()

    def test_discover_markdown_files_directory(self):
        """Tests that recursive discovery locates *.md files while skipping templates directory."""
        files = discover_markdown_files(self.test_root)
        file_names = [f.name for f in files]

        self.assertIn("receive_test.md", file_names)
        self.assertIn("broken_test.md", file_names)
        self.assertNotIn("template_test.md", file_names)

    def test_discover_markdown_files_single_file(self):
        """Tests that explicit single file discovery works for any markdown file."""
        files = discover_markdown_files(self.valid_file)
        self.assertEqual(len(files), 1)
        self.assertEqual(files[0].name, "receive_test.md")

    def test_derive_department_from_path(self):
        """Tests that department_id is derived correctly from parent directory name."""
        self.assertEqual(derive_department_from_path(self.inbound_dir / "doc.md"), "dept_inbound")
        self.assertEqual(derive_department_from_path(self.test_root / "quality" / "doc.md"), "dept_quality")
        self.assertEqual(derive_department_from_path(self.test_root / "unknown" / "doc.md"), "dept_operations")

    @patch("scripts.load_owd.OWDLoader.get_workflow_version_by_hash")
    @patch("scripts.load_owd.OWDLoader.get_latest_version_number")
    @patch("scripts.load_owd.OWDLoader.load")
    def test_single_workflow_load_success(self, mock_load, mock_get_ver, mock_get_hash):
        """Tests end-to-end processing of a valid single OWD specification."""
        mock_get_hash.return_value = None
        mock_get_ver.return_value = 0
        mock_load.return_value = MagicMock(success=True, tables_updated=["KNOWLEDGE_STUDIO.workflows"])

        res = process_single_owd(self.valid_file, logger=self.logger_mock, skip_loader=False)

        self.assertEqual(res["status"], "SUCCESS")
        self.assertEqual(res["workflow_code"], "SOP_TEST_001")
        self.assertEqual(res["states"], 2)
        self.assertEqual(res["steps"], 1)
        self.assertEqual(res["rules"], 1)
        self.assertEqual(res["version"], 1)
        mock_load.assert_called_once()

    @patch("scripts.load_owd.OWDLoader.get_workflow_version_by_hash")
    def test_duplicate_hash_detection_skips_deployment(self, mock_get_hash):
        """Tests that SHA256 duplicate detection skips re-deploying identical OWD content."""
        mock_get_hash.return_value = {"id": "ver_001", "version_number": 1, "ast_hash": "mock_hash"}

        res = process_single_owd(self.valid_file, logger=self.logger_mock, skip_loader=False)

        self.assertEqual(res["status"], "SKIPPED")
        self.assertIn("Duplicate source hash", res["reason"])
        self.assertEqual(res["version"], 1)

    @patch("scripts.load_owd.OWDLoader.get_workflow_version_by_hash")
    @patch("scripts.load_owd.OWDLoader.get_latest_version_number")
    @patch("scripts.load_owd.OWDLoader.load")
    def test_version_increment_on_hash_change(self, mock_load, mock_get_ver, mock_get_hash):
        """Tests that content modification increments version_number from 1 to 2."""
        mock_get_hash.return_value = None  # New hash
        mock_get_ver.return_value = 1       # Existing max version = 1
        mock_load.return_value = MagicMock(success=True)

        res = process_single_owd(self.valid_file, logger=self.logger_mock, skip_loader=False)

        self.assertEqual(res["status"], "SUCCESS")
        self.assertEqual(res["version"], 2)

    def test_validation_failure_isolation(self):
        """Tests that invalid OWD files fail validation and record errors without throwing uncaught exceptions."""
        res = process_single_owd(self.invalid_file, logger=self.logger_mock, skip_loader=True)

        self.assertEqual(res["status"], "FAILED")
        self.assertIn("Validation checks failed", res["reason"])
        self.assertGreaterEqual(len(res["validation_errors"]), 1)

    @patch("scripts.load_owd.OWDLoader.get_workflow_version_by_hash")
    @patch("scripts.load_owd.OWDLoader.get_latest_version_number")
    @patch("scripts.load_owd.OWDLoader.load")
    def test_snowflake_rollback_error_handling(self, mock_load, mock_get_ver, mock_get_hash):
        """Tests that Snowflake database loading errors trigger rollback handling and record error details."""
        mock_get_hash.return_value = None
        mock_get_ver.return_value = 0
        mock_load.side_effect = OWDLoaderException("Snowflake connection timeout or constraint error.")

        res = process_single_owd(self.valid_file, logger=self.logger_mock, skip_loader=False)

        self.assertEqual(res["status"], "FAILED")
        self.assertIn("Snowflake Loader Error", res["reason"])
        self.assertGreaterEqual(len(res["snowflake_errors"]), 1)

    def test_deployment_reports_generation(self):
        """Tests that JSON and Markdown deployment report files are generated correctly."""
        results = [
            {
                "file_path": "knowledge-engine/owd_repository/inbound/receive_shipment.md",
                "title": "Inbound Shipment Receiving Procedure",
                "workflow_code": "SOP_INB_001",
                "states": 6,
                "steps": 9,
                "rules": 2,
                "decisions": 0,
                "warnings": 0,
                "version": 1,
                "hash": "a24f519f",
                "status": "SUCCESS",
                "reason": "",
                "validation_errors": [],
                "compilation_errors": [],
                "snowflake_errors": [],
                "elapsed_sec": 1.25,
            }
        ]

        write_report_files(results, total_elapsed_sec=1.25, output_dir=self.test_root)

        json_file = self.test_root / "deployment_report.json"
        md_file = self.test_root / "deployment_report.md"

        self.assertTrue(json_file.exists())
        self.assertTrue(md_file.exists())

        report_json = json.loads(json_file.read_text(encoding="utf-8"))
        self.assertEqual(report_json["total_workflows"], 1)
        self.assertEqual(report_json["workflows_loaded"], 1)

        md_content = md_file.read_text(encoding="utf-8")
        self.assertIn("Owd Deployment Report", md_content.title())
        self.assertIn("SOP_INB_001", md_content)


if __name__ == "__main__":
    unittest.main()
