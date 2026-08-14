"""OWD Ingestion Pipeline CLI & Service.

Official enterprise loader for compiling and deploying OWD Markdown SOP specifications into
normalized Snowflake KNOWLEDGE_STUDIO tables.

Usage:
  python scripts/load_owd.py knowledge-engine/owd_repository/inbound/receive_shipment.md
  python scripts/load_owd.py knowledge-engine/owd_repository/
"""

import os
import sys
import json
import time
import logging
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Tuple, Optional
from app.core.config import settings

# Ensure root directory and backend/knowledge-engine are in Python path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))
backend_dir = ROOT_DIR / "backend"
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))
knowledge_engine_dir = ROOT_DIR / "knowledge-engine"
if str(knowledge_engine_dir) not in sys.path:
    sys.path.insert(0, str(knowledge_engine_dir))

from app.compiler.pipeline import OWDCompilerPipeline
from app.compiler.parser import OWDParser
from app.compiler.validator import OWDValidator
from app.compiler.loader import OWDLoader
from app.compiler.models import OWDDocument, ValidationReport
from app.compiler.utils import calculate_source_hash
from app.compiler.exceptions import OWDParsingException, OWDLoaderException
from app.compiler.utils import generate_deterministic_uuid
from app.repositories.knowledge_repository import KnowledgeRepository
from app.services.ingestion import IngestionService


def setup_deployment_logger() -> Tuple[logging.Logger, Path]:
    """Creates logs/ directory and configures timestamped deployment log file."""
    logs_dir = ROOT_DIR / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)

    timestamp_str = datetime.now().strftime("%Y%m%d_%H%M")
    log_file_path = logs_dir / f"deployment_{timestamp_str}.log"

    logger = logging.getLogger("owd_ingestion")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    # File handler
    file_handler = logging.FileHandler(log_file_path, encoding="utf-8")
    file_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    logger.addHandler(file_handler)

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    logger.addHandler(console_handler)

    return logger, log_file_path


def discover_markdown_files(target_path: Path) -> List[Path]:
    """Recursively discovers OWD *.md files from single file or repository directory."""
    if not target_path.exists():
        raise FileNotFoundError(f"Specified path does not exist: {target_path}")

    if target_path.is_file():
        if target_path.suffix.lower() == ".md":
            return [target_path]
        return []

    discovered: List[Path] = []
    for root, dirs, files in os.walk(target_path):
        # Skip templates directory when scanning an entire repository directory
        if "templates" in dirs and target_path.resolve() != (target_path / "templates").resolve():
            dirs.remove("templates")
        for f in files:
            if f.lower().endswith(".md"):
                discovered.append(Path(root) / f)

    return sorted(discovered)


def derive_department_from_path(file_path: Path) -> str:
    """Derives department_id from repository parent directory name."""
    parent_name = file_path.parent.name.lower()
    dept_map = {
        "inbound": "dept_inbound",
        "outbound": "dept_outbound",
        "inventory": "dept_inventory",
        "quality": "dept_quality",
        "safety": "dept_safety",
        "returns": "dept_returns",
        "maintenance": "dept_maintenance",
    }
    return dept_map.get(parent_name, "dept_operations")


def process_single_owd(
    file_path: Path,
    logger: Optional[logging.Logger] = None,
    skip_loader: bool = False,
) -> Dict[str, Any]:
    """Processes a single OWD markdown file: hash-duplicate check, version increment, compile, and load."""
    if logger is None:
        logger = logging.getLogger("owd_ingestion")

    start_time = time.time()
    try:
        relative_path = str(file_path.relative_to(ROOT_DIR))
    except ValueError:
        relative_path = str(file_path.name)
    logger.info(f"Processing OWD file: {relative_path}")

    # --- Read file ---
    try:
        raw_text = file_path.read_text(encoding="utf-8")
    except Exception as exc:
        return {
            "file_path": relative_path,
            "title": file_path.stem.replace("_", " ").title(),
            "workflow_code": f"SOP-{file_path.stem.upper()[:10]}",
            "states": 0, "steps": 0, "rules": 0, "decisions": 0, "warnings": 0,
            "version": 1, "hash": "",
            "status": "FAILED",
            "reason": f"Failed to read file: {exc}",
            "validation_errors": [], "compilation_errors": [str(exc)], "snowflake_errors": [],
            "elapsed_sec": round(time.time() - start_time, 3),
        }

    source_hash = calculate_source_hash(raw_text)
    department_id = derive_department_from_path(file_path)
    prepared_document: Optional[OWDDocument] = None
    validation: Optional[ValidationReport] = None

    try:
        prepared_document = OWDParser.parse(
            markdown_text=raw_text,
            title=file_path.stem.replace("_", " ").title(),
            department_id=department_id,
            default_version=1,
        )
        validation = OWDValidator.validate(prepared_document)
    except OWDParsingException as exc:
        validation = None
        parse_error = exc.message
    else:
        parse_error = ""

    if parse_error or not validation or not validation.is_valid:
        errors = [parse_error] if parse_error else (validation.errors if validation else [])
        return {
            "file_path": relative_path,
            "title": file_path.stem.replace("_", " ").title(),
            "workflow_code": (
                prepared_document.workflow.workflow_code if prepared_document else ""
            ),
            "states": validation.states_count if validation else 0,
            "steps": validation.steps_count if validation else 0,
            "rules": 0,
            "decisions": validation.decisions_count if validation else 0,
            "warnings": len(validation.warnings) if validation else 0,
            "version": 1,
            "hash": source_hash,
            "status": "FAILED",
            "reason": "; ".join(errors),
            "validation_errors": errors,
            "compilation_errors": [],
            "snowflake_errors": [],
            "elapsed_sec": round(time.time() - start_time, 3),
        }

    assert prepared_document is not None
    assert validation is not None
    workflow_code = prepared_document.workflow.workflow_code
    workflow_id = generate_deterministic_uuid("workflow", workflow_code)

    # --- Resolve all database identity/version/staging inputs before compilation ---
    version_number = 1
    stage_file_uri = ""
    try:
        if not skip_loader:
            if not KnowledgeRepository.department_exists(department_id):
                raise OWDLoaderException(f"Unknown or inactive department '{department_id}'.")
            existing = OWDLoader.get_workflow_version_by_hash(workflow_code, source_hash)
            if existing:
                logger.info(f"Duplicate source hash detected for '{relative_path}'. Skipping deployment.")
                return {
                    "file_path": relative_path,
                    "title": file_path.stem.replace("_", " ").title(),
                    "workflow_code": workflow_code,
                    "states": 0, "steps": 0, "rules": 0, "decisions": 0, "warnings": 0,
                    "version": existing.get("version_number", 1),
                    "hash": source_hash,
                    "status": "SKIPPED",
                    "reason": f"Duplicate source hash: content identical to version {existing.get('version_number', 1)}.",
                    "validation_errors": [], "compilation_errors": [], "snowflake_errors": [],
                    "elapsed_sec": round(time.time() - start_time, 3),
                }
            version_number = KnowledgeRepository.get_next_version_number(workflow_id)
            stage_file_uri = IngestionService.stage_file(
                file_path.read_bytes(),
                file_path.name,
                f"{workflow_code}/v{version_number}/{source_hash[:12]}",
            )
    except Exception as exc:
        message = getattr(exc, "message", str(exc))
        logger.error(f"Snowflake preparation error for '{relative_path}': {message}")
        return {
            "file_path": relative_path,
            "title": file_path.stem.replace("_", " ").title(),
            "workflow_code": workflow_code,
            "states": validation.states_count,
            "steps": validation.steps_count,
            "rules": 0,
            "decisions": validation.decisions_count,
            "warnings": len(validation.warnings),
            "version": version_number,
            "hash": source_hash,
            "status": "FAILED",
            "reason": f"Snowflake preparation error: {message}",
            "validation_errors": [],
            "compilation_errors": [],
            "snowflake_errors": [message],
            "elapsed_sec": round(time.time() - start_time, 3),
        }
    prepared_document.workflow.version_number = version_number

    # --- Run full pipeline (parse → validate → compile → load) ---
    try:
        report = OWDCompilerPipeline.process_owd(
            markdown_text=raw_text,
            department_id=department_id,
            version_number=version_number,
            skip_loader=skip_loader,
            prepared_document=prepared_document,
            stage_file_uri=stage_file_uri,
            source_filename=file_path.name,
            user_id=settings.OWD_CLI_USER_ID,
        )
    except OWDLoaderException as load_err:
        logger.error(f"Snowflake Loader Error for '{relative_path}': {load_err.message}")
        return {
            "file_path": relative_path,
            "title": file_path.stem.replace("_", " ").title(),
            "workflow_code": "",
            "states": 0, "steps": 0, "rules": 0, "decisions": 0, "warnings": 0,
            "version": version_number, "hash": source_hash,
            "status": "FAILED",
            "reason": f"Snowflake Loader Error: {load_err.message}",
            "validation_errors": [], "compilation_errors": [],
            "snowflake_errors": [load_err.message],
            "elapsed_sec": round(time.time() - start_time, 3),
        }

    comp_status = report.get("compilation_status", "FAILED")

    # Map VALIDATION_FAILED to user-facing reason
    if comp_status == "VALIDATION_FAILED":
        val_errors = report.get("validation_errors", [])
        return {
            "file_path": relative_path,
            "title": file_path.stem.replace("_", " ").title(),
            "workflow_code": report.get("workflow_code", ""),
            "states": report.get("number_of_states", 0),
            "steps": report.get("number_of_steps", 0),
            "rules": report.get("number_of_safety_rules", 0) + report.get("number_of_business_rules", 0),
            "decisions": report.get("number_of_decisions", 0),
            "warnings": len(report.get("warnings", [])),
            "version": version_number, "hash": source_hash,
            "status": "FAILED",
            "reason": f"Validation checks failed: {'; '.join(val_errors[:2])}",
            "validation_errors": val_errors, "compilation_errors": [], "snowflake_errors": [],
            "elapsed_sec": round(time.time() - start_time, 3),
        }

    if comp_status != "SUCCESS":
        return {
            "file_path": relative_path,
            "title": file_path.stem.replace("_", " ").title(),
            "workflow_code": report.get("workflow_code", ""),
            "states": 0, "steps": 0, "rules": 0, "decisions": 0, "warnings": 0,
            "version": version_number, "hash": source_hash,
            "status": "FAILED",
            "reason": "; ".join(report.get("validation_errors", ["Pipeline failure"])),
            "validation_errors": report.get("validation_errors", []),
            "compilation_errors": report.get("compilation_errors", []),
            "snowflake_errors": [],
            "elapsed_sec": round(time.time() - start_time, 3),
        }

    return {
        "file_path": relative_path,
        "title": report.get("title", file_path.stem.replace("_", " ").title()),
        "workflow_code": report.get("workflow_code", f"SOP-{file_path.stem.upper()[:10]}"),
        "states": report.get("number_of_states", 0),
        "steps": report.get("number_of_steps", 0),
        "rules": report.get("number_of_safety_rules", 0) + report.get("number_of_business_rules", 0),
        "decisions": report.get("number_of_decisions", 0),
        "warnings": len(report.get("warnings", [])),
        "version": report.get("version_number", version_number),
        "hash": report.get("ast_hash", source_hash),
        "status": "SUCCESS",
        "reason": "",
        "validation_errors": [], "compilation_errors": [], "snowflake_errors": [],
        "elapsed_sec": round(time.time() - start_time, 3),
    }


def print_workflow_report(res: Dict[str, Any]):
    """Prints single workflow deployment block (Part 6)."""
    title = res["title"]
    print("====================================================\n")
    print(f"{title}\n")
    print(f"States ............. {res['states']}")
    print(f"Steps .............. {res['steps']}")
    print(f"Rules .............. {res['rules']}")
    print(f"Decisions .......... {res['decisions']}")
    print(f"Warnings ........... {res['warnings']}")
    print(f"Deployment ......... {res['status']}\n")
    print("----------------------------------------------------\n")


def print_overall_summary(
    results: List[Dict[str, Any]],
    total_elapsed_sec: float,
):
    """Prints final summary block (Part 6)."""
    loaded_count = sum(1 for r in results if r["status"] == "SUCCESS")
    skipped_count = sum(1 for r in results if r["status"] == "SKIPPED")
    failed_count = sum(1 for r in results if r["status"] == "FAILED")
    total_states = sum(r["states"] for r in results if r["status"] in ("SUCCESS", "SKIPPED"))
    total_steps = sum(r["steps"] for r in results if r["status"] in ("SUCCESS", "SKIPPED"))
    total_rules = sum(r["rules"] for r in results if r["status"] in ("SUCCESS", "SKIPPED"))

    print("Summary\n")
    print(f"Workflows Loaded ..... {loaded_count}")
    print(f"States ............... {total_states}")
    print(f"Steps ................ {total_steps}")
    print(f"Rules ................ {total_rules}")
    print(f"Skipped .............. {skipped_count}")
    print(f"Failed ............... {failed_count}")
    print(f"Execution Time ....... {round(total_elapsed_sec, 2)} sec\n")
    print("====================================================\n")


def write_report_files(
    results: List[Dict[str, Any]],
    total_elapsed_sec: float,
    output_dir: Path,
):
    """Writes deployment_report.json and deployment_report.md files (Part 7)."""
    output_dir.mkdir(parents=True, exist_ok=True)

    loaded_count = sum(1 for r in results if r["status"] == "SUCCESS")
    skipped_count = sum(1 for r in results if r["status"] == "SKIPPED")
    failed_count = sum(1 for r in results if r["status"] == "FAILED")

    summary_data = {
        "timestamp": datetime.now().isoformat(),
        "total_workflows": len(results),
        "workflows_loaded": loaded_count,
        "workflows_skipped": skipped_count,
        "workflows_failed": failed_count,
        "total_states": sum(r["states"] for r in results if r["status"] in ("SUCCESS", "SKIPPED")),
        "total_steps": sum(r["steps"] for r in results if r["status"] in ("SUCCESS", "SKIPPED")),
        "total_rules": sum(r["rules"] for r in results if r["status"] in ("SUCCESS", "SKIPPED")),
        "total_execution_time_sec": round(total_elapsed_sec, 3),
        "results": results,
    }

    # JSON report
    json_path = output_dir / "deployment_report.json"
    json_path.write_text(json.dumps(summary_data, indent=2), encoding="utf-8")

    # Markdown report
    md_lines = [
        "# OWD Deployment Report",
        "",
        f"**Date**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"**Total Workflows**: {len(results)} | **Loaded**: {loaded_count} | **Skipped**: {skipped_count} | **Failed**: {failed_count}",
        f"**Execution Time**: {round(total_elapsed_sec, 2)}s",
        "",
        "## Summary Metrics",
        "",
        "| Metric | Count |",
        "|---|---|",
        f"| Workflows Loaded | {loaded_count} |",
        f"| Workflows Skipped | {skipped_count} |",
        f"| Workflows Failed | {failed_count} |",
        f"| Total States | {summary_data['total_states']} |",
        f"| Total Steps | {summary_data['total_steps']} |",
        f"| Total Rules | {summary_data['total_rules']} |",
        "",
        "## Detailed Results",
        "",
        "| Workflow Code | Title | Status | States | Steps | Rules | Version | File |",
        "|---|---|---|---|---|---|---|---|",
    ]

    for r in results:
        md_lines.append(
            f"| `{r['workflow_code']}` | {r['title']} | **{r['status']}** | {r['states']} | {r['steps']} | {r['rules']} | v{r['version']} | `{r['file_path']}` |"
        )

    if failed_count > 0:
        md_lines.extend(["", "## Failure Details", ""])
        for r in results:
            if r["status"] == "FAILED":
                md_lines.append(f"### ❌ `{r['workflow_code']}` — {r['title']}")
                md_lines.append(f"**Reason**: {r['reason']}")
                if r["validation_errors"]:
                    md_lines.append("**Validation Errors**:")
                    for err in r["validation_errors"]:
                        md_lines.append(f"- {err}")
                if r["compilation_errors"]:
                    md_lines.append("**Compilation Errors**:")
                    for err in r["compilation_errors"]:
                        md_lines.append(f"- {err}")
                if r["snowflake_errors"]:
                    md_lines.append("**Snowflake Errors**:")
                    for err in r["snowflake_errors"]:
                        md_lines.append(f"- {err}")
                md_lines.append("")

    md_content = "\n".join(md_lines)
    (output_dir / "deployment_report.md").write_text(md_content, encoding="utf-8")


def run_ingestion_pipeline(
    target_path: Path,
    skip_loader: bool = False,
) -> Dict[str, Any]:
    """Main entry point orchestrating OWD ingestion pipeline."""
    start_total = time.time()
    logger, log_file_path = setup_deployment_logger()

    logger.info("====================================================")
    logger.info("Starting WorkMate AI OWD Ingestion Pipeline")
    logger.info(f"Target Path: {target_path}")
    logger.info("====================================================")

    discovered_files = discover_markdown_files(target_path)
    if not discovered_files:
        logger.warning(f"No OWD markdown (*.md) files found at target path: {target_path}")
        print(f"No OWD markdown (*.md) files found at target path: {target_path}")
        return {"total_workflows": 0, "results": []}

    logger.info(f"Discovered {len(discovered_files)} OWD markdown specification file(s).")

    results: List[Dict[str, Any]] = []
    for file_path in discovered_files:
        res = process_single_owd(file_path, logger=logger, skip_loader=skip_loader)
        results.append(res)
        print_workflow_report(res)

    total_elapsed = time.time() - start_total
    print_overall_summary(results, total_elapsed)

    logs_dir = ROOT_DIR / "logs"
    write_report_files(results, total_elapsed, logs_dir)

    logger.info(f"OWD Ingestion Pipeline completed in {round(total_elapsed, 2)}s.")
    logger.info(f"Log file generated: {log_file_path}")
    logger.info(f"Report files generated in: {logs_dir}")

    return {
        "total_workflows": len(results),
        "results": results,
        "elapsed_sec": round(total_elapsed, 3),
        "log_file": str(log_file_path),
    }


if __name__ == "__main__":
    if len(sys.argv) > 1:
        raw_target = sys.argv[1]
        target = Path(raw_target).resolve()
    else:
        target = ROOT_DIR / "knowledge-engine" / "owd_repository"

    run_ingestion_pipeline(target)
