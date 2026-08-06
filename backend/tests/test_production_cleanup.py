"""Regression tests for removal of abandoned deployment and ingestion fallbacks."""

import subprocess
import sys
from pathlib import Path

from app.repositories.knowledge_repository import KnowledgeRepository
from app.compiler.parsers.retrieval_metadata_parser import RetrievalMetadataParser
from backend.scripts.seed_test_users import SEED_USERS
from scripts import deploy_owd_schema


def test_legacy_generic_chunk_writers_are_not_exposed():
    assert not hasattr(KnowledgeRepository, "save_chunks")
    assert not hasattr(KnowledgeRepository, "insert_document_chunks")


def test_demo_employee_uses_a_migration_backed_content_department():
    employee = next(user for user in SEED_USERS if user["role_name"] == "employee")
    assert employee["department_id"] == "dept_ops"


def test_retrieval_metadata_does_not_fabricate_embedding_or_index_state():
    metadata = RetrievalMetadataParser.parse("# Operational workflow")
    assert metadata.embedding_metadata == {}
    assert metadata.vector_metadata == {}
    assert metadata.cortex_search_metadata == {}


def test_deployment_orders_runtime_alignment_and_separates_cortex(monkeypatch):
    assert deploy_owd_schema.MIGRATION_FILES[-1] == "12_runtime_alignment.sql"
    assert "11_cortex_search_service.sql" not in deploy_owd_schema.MIGRATION_FILES
    assert deploy_owd_schema.CORTEX_SEARCH_MIGRATION == "11_cortex_search_service.sql"
    monkeypatch.setattr(
        deploy_owd_schema.settings,
        "SNOWFLAKE_ACCOUNT",
        "your_snowflake_account_placeholder",
    )

    report = deploy_owd_schema.deploy_migrations()

    assert report["status"] == "FAILED"
    assert report["failed_statements"]
    assert report["schemas_created"] == []


def test_runtime_alignment_migration_matches_department_contract():
    migration = Path("analytics/migrations/12_runtime_alignment.sql").read_text(encoding="utf-8")
    assert "ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE" in migration
    assert "SET is_active = TRUE" in migration
    for department_id in (
        "dept_admin", "dept_inbound", "dept_ops", "dept_quality",
        "dept_inventory", "dept_eng",
    ):
        assert department_id in migration


def test_fresh_security_schema_and_container_match_v2_architecture():
    security_sql = Path("analytics/migrations/02_security.sql").read_text(encoding="utf-8")
    dockerfile = Path("infra/docker/backend.Dockerfile").read_text(encoding="utf-8")
    assert "is_active BOOLEAN NOT NULL DEFAULT TRUE" in security_sql
    assert "knowledge-engine" not in dockerfile


def test_deployment_cli_returns_failure_for_placeholder_credentials():
    result = subprocess.run(
        [sys.executable, "scripts/deploy_owd_schema.py"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    assert "Status: FAILED" in result.stdout


def test_live_deployment_error_never_becomes_mock_success(monkeypatch):
    monkeypatch.setattr(deploy_owd_schema.settings, "SNOWFLAKE_ACCOUNT", "real-account")

    def connection_failure():
        raise RuntimeError("Snowflake unavailable")

    monkeypatch.setattr(deploy_owd_schema, "get_snowflake_connection", connection_failure)
    report = deploy_owd_schema.deploy_migrations()

    assert report["status"] == "FAILED"
    assert report["schemas_created"] == []
    assert "Snowflake unavailable" in report["failed_statements"][0]["error"]
