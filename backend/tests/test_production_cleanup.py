"""Regression tests for removal of abandoned deployment and ingestion fallbacks."""

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
    assert metadata.semantic_search_metadata == {}


def test_deployment_order_contains_database_only_prerequisites(monkeypatch):
    assert deploy_owd_schema.MIGRATION_FILES[-2:] == [
        "12_runtime_alignment.sql",
        "13_runtime_prerequisites.sql",
    ]
    assert deploy_owd_schema.ordered_migrations() == deploy_owd_schema.MIGRATION_FILES
    monkeypatch.setattr(
        deploy_owd_schema.settings,
        "SNOWFLAKE_ACCOUNT",
        "your_snowflake_account_placeholder",
    )

    report = deploy_owd_schema.deploy_migrations()

    assert report["status"] == "FAILED"
    assert report["failed_statements"]
    assert report["schemas_created"] == []


def test_deployment_rejects_sanitized_template_credentials(monkeypatch):
    monkeypatch.setattr(deploy_owd_schema.settings, "SNOWFLAKE_ACCOUNT", "your_snowflake_account")
    monkeypatch.setattr(deploy_owd_schema.settings, "SNOWFLAKE_USER", "your_snowflake_user")
    monkeypatch.setattr(deploy_owd_schema.settings, "SNOWFLAKE_PASSWORD", "replace_with_a_local_secret")

    assert deploy_owd_schema.has_placeholder_credentials() is True
