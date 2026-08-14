"""OWD Compiler Pipeline Orchestrator.

Wires Parser -> Validator -> Compiler -> Loader into a clean end-to-end processing pipeline.
Generates comprehensive compilation reports for Knowledge Studio upload endpoints.
"""

import logging
from typing import Dict, Any, Optional

from app.compiler.parser import OWDParser
from app.compiler.validator import OWDValidator
from app.compiler.compiler import OWDCompiler
from app.compiler.loader import OWDLoader
from app.compiler.models import OWDDocument, ValidationReport, CompiledWorkflow, LoadResult
from app.compiler.exceptions import (
    OWDParsingException,
    OWDCompilationException,
    OWDLoaderException,
)

logger = logging.getLogger("compiler.pipeline")


class OWDCompilerPipeline:
    """End-to-end execution pipeline for compiling OWD Markdown files into Snowflake executable state graphs."""

    @staticmethod
    def process_owd(
        markdown_text: str,
        workflow_code: str = "",
        title: str = "",
        department_id: str = "dept_general",
        category: str = "OPERATIONAL_SOP",
        user_id: str = "admin",
        stage_file_uri: str = "",
        version_number: int = 1,
        skip_loader: bool = False,
        prepared_document: Optional[OWDDocument] = None,
        source_filename: str = "",
    ) -> Dict[str, Any]:
        """Executes Parser -> Validator -> Compiler -> Loader pipeline and returns detailed compilation report."""
        logger.info("[STAGE 0 INIT] Processing OWD Markdown (%d characters)", len(markdown_text))

        # 1. PARSE STAGE
        try:
            owd_doc: OWDDocument = prepared_document or OWDParser.parse(
                markdown_text=markdown_text,
                workflow_code=workflow_code,
                title=title,
                department_id=department_id,
                category=category,
                default_version=version_number,
            )
            parsed_states_cnt = len(owd_doc.workflow.states)
            parsed_steps_cnt = sum(len(s.steps) for s in owd_doc.workflow.states)
            logger.info(
                "[STAGE 1 PARSE COMPLETE] UnifiedAST assembled for '%s': "
                "%d states and %d steps parsed.",
                owd_doc.workflow.workflow_code,
                parsed_states_cnt,
                parsed_steps_cnt,
            )
        except OWDParsingException as parse_err:
            logger.error(f"[PIPELINE STAGE 1 PARSE FAILED] {parse_err.message}")
            return {
                "compilation_status": "PARSING_FAILED",
                "validation_errors": [parse_err.message],
                "warnings": [],
                "number_of_states": 0,
                "number_of_steps": 0,
                "number_of_decisions": 0,
                "number_of_business_rules": 0,
                "number_of_safety_rules": 0,
                "number_of_validation_rules": 0,
                "deployment_status": "FAILED",
                "snowflake_tables_updated": [],
                "workflow_id": "",
                "version_id": "",
                "version_number": version_number,
                "stage_file_uri": stage_file_uri,
            }

        # 2. VALIDATE STAGE
        val_report: ValidationReport = OWDValidator.validate(owd_doc)
        logger.info(f"[STAGE 2 VALIDATE COMPLETE] Report valid={val_report.is_valid}. Errors: {val_report.errors}, Warnings: {val_report.warnings}")
        if not val_report.is_valid:
            logger.warning(f"[PIPELINE STAGE 2 VALIDATION FAILED] {len(val_report.errors)} validation errors detected.")
            return {
                "compilation_status": "VALIDATION_FAILED",
                "validation_errors": val_report.errors,
                "warnings": val_report.warnings,
                "number_of_states": val_report.states_count,
                "number_of_steps": val_report.steps_count,
                "number_of_decisions": val_report.decisions_count,
                "number_of_business_rules": val_report.business_rules_count,
                "number_of_safety_rules": val_report.safety_rules_count,
                "number_of_validation_rules": val_report.validation_rules_count,
                "deployment_status": "FAILED",
                "snowflake_tables_updated": [],
                "workflow_id": "",
                "version_id": "",
                "version_number": version_number,
                "stage_file_uri": stage_file_uri,
            }

        # 3. COMPILE STAGE
        try:
            compiled_wf: CompiledWorkflow = OWDCompiler.compile(
                owd_document=owd_doc,
                stage_file_uri=stage_file_uri,
                user_id=user_id,
                source_filename=source_filename,
            )
            logger.info(f"[STAGE 3 COMPILE COMPLETE] CompiledWorkflow generated. Workflow ID: {compiled_wf.workflow_payload.get('id')}, Version ID: {compiled_wf.version_payload.get('id')}, AST Hash: {compiled_wf.version_payload.get('ast_hash')}")
        except OWDCompilationException as comp_err:
            logger.error(f"[PIPELINE STAGE 3 COMPILE FAILED] {comp_err.message}")
            return {
                "compilation_status": "COMPILATION_ERROR",
                "validation_errors": [comp_err.message],
                "warnings": val_report.warnings,
                "number_of_states": val_report.states_count,
                "number_of_steps": val_report.steps_count,
                "number_of_decisions": val_report.decisions_count,
                "number_of_business_rules": val_report.business_rules_count,
                "number_of_safety_rules": val_report.safety_rules_count,
                "number_of_validation_rules": val_report.validation_rules_count,
                "deployment_status": "FAILED",
                "snowflake_tables_updated": [],
                "workflow_id": "",
                "version_id": "",
                "version_number": version_number,
                "stage_file_uri": stage_file_uri,
            }

        # 4. LOAD STAGE (Snowflake Database Insertion)
        tables_updated = []
        workflow_id = compiled_wf.workflow_payload.get("id", "")
        version_id = compiled_wf.version_payload.get("id", "")
        deployment_status = "STAGED"

        if not skip_loader:
            try:
                load_res: LoadResult = OWDLoader.load(compiled_wf)
                tables_updated = load_res.tables_updated
                deployment_status = "PUBLISHED"
                logger.info(f"[STAGE 4 LOAD COMPLETE] OWDLoader.load succeeded. Tables updated: {tables_updated}")
            except OWDLoaderException as load_err:
                logger.error(f"[PIPELINE STAGE 4 LOAD FAILED] Snowflake insertion failed: {load_err.message}")
                raise load_err

        logger.info(f"[COMPILER PIPELINE SUCCESS] OWD '{owd_doc.workflow.workflow_code}' compiled & deployed successfully.")

        return {
            "compilation_status": "SUCCESS",
            "validation_errors": [],
            "warnings": val_report.warnings,
            "number_of_states": val_report.states_count,
            "number_of_steps": val_report.steps_count,
            "number_of_decisions": val_report.decisions_count,
            "number_of_business_rules": val_report.business_rules_count,
            "number_of_safety_rules": val_report.safety_rules_count,
            "number_of_validation_rules": val_report.validation_rules_count,
            "deployment_status": deployment_status,
            "snowflake_tables_updated": tables_updated,
            "workflow_id": workflow_id,
            "workflow_code": owd_doc.workflow.workflow_code,
            "version_id": version_id,
            "version_number": version_number,
            "stage_file_uri": stage_file_uri,
        }
