"""Regression tests for removal of abandoned deployment and ingestion fallbacks."""

import subprocess
import sys

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


def test_deployment_includes_cortex_search_and_fails_closed(monkeypatch):
    assert deploy_owd_schema.MIGRATION_FILES[-1] == "11_cortex_search_service.sql"
    monkeypatch.setattr(
        deploy_owd_schema.settings,
        "SNOWFLAKE_ACCOUNT",
        "your_snowflake_account_placeholder",
    )

    report = deploy_owd_schema.deploy_migrations()

    assert report["status"] == "FAILED"
    assert report["failed_statements"]
    assert report["schemas_created"] == []


def test_deployment_cli_returns_failure_for_placeholder_credentials():
    result = subprocess.run(
        [sys.executable, "scripts/deploy_owd_schema.py"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    assert "Status: FAILED" in result.stdout
