"""Regression tests for removal of abandoned deployment and ingestion fallbacks."""

from unittest.mock import MagicMock

from app.repositories.knowledge_repository import KnowledgeRepository
from app.compiler.parsers.retrieval_metadata_parser import RetrievalMetadataParser
from backend.scripts.seed_test_users import SEED_USERS
from scripts import deploy_owd_schema


def test_legacy_generic_chunk_writers_are_not_exposed():
    assert not hasattr(KnowledgeRepository, "save_chunks")
    assert not hasattr(KnowledgeRepository, "insert_document_chunks")


def test_demo_employee_uses_a_migration_backed_content_department():
    employee = next(user for user in SEED_USERS if user["email"] == "employee@workmate.ai")
    assert employee["department_id"] == "dept_ops"


def test_seed_users_cover_both_retrieval_departments():
    employee_departments = {
        user["department_id"]
        for user in SEED_USERS
        if user["role_name"] == "employee"
    }

    assert {"dept_ops", "dept_inbound"} <= employee_departments


def test_retrieval_metadata_does_not_fabricate_embedding_or_index_state():
    metadata = RetrievalMetadataParser.parse("# Operational workflow")
    assert metadata.embedding_metadata == {}
    assert metadata.vector_metadata == {}
    assert metadata.semantic_search_metadata == {}


def test_postgres_deployment_orders_security_and_pilot_migrations_and_rejects_shared_login():
    from scripts.migrate_postgres import MIGRATIONS, select_migration_url
    import pytest

    files = sorted(path.name for path in MIGRATIONS.glob("[0-9][0-9][0-9]_*.sql"))
    assert files and files == sorted(files)
    assert "003_security_sessions_rls.sql" in files
    assert "004_pilot_feedback.sql" in files
    with pytest.raises(ValueError, match="distinct login"):
        select_migration_url({
            "APP_ENV": "staging",
            "MIGRATION_DATABASE_URL": "postgresql://same:pass@localhost:5432/workmate",
            "DATABASE_URL": "postgresql://same:pass@localhost:5432/workmate",
        })


def test_active_version_migration_deprecates_stale_retrieval_rows():
    sql = (
        deploy_owd_schema.MIGRATIONS_DIR / "15_active_workflow_versions.sql"
    ).read_text(encoding="utf-8")

    assert "ROW_NUMBER() OVER" in sql
    assert "UPDATE KNOWLEDGE_STUDIO.workflow_versions AS target" in sql
    assert "WHERE target.id = stale.id" in sql
    assert "SET status = 'deprecated'" in sql
    assert "SET status = 'archived'" in sql
    assert "LOWER(version.status) <> 'published'" in sql
    assert "SET department_id = workflow.department_id" in sql


def test_flexible_authoring_migration_preserves_descriptive_metadata():
    sql = (
        deploy_owd_schema.MIGRATIONS_DIR
        / "16_flexible_owd_authoring_metadata.sql"
    ).read_text(encoding="utf-8")

    assert "estimated_duration SET DATA TYPE VARCHAR(512)" in sql
    assert "review_cycle SET DATA TYPE VARCHAR(512)" in sql


def test_production_configuration_rejects_placeholder_postgres_credentials(monkeypatch):
    import pytest
    from app.core.config import Settings

    monkeypatch.setenv("JWT_SECRET", "a" * 40)
    monkeypatch.setenv("INTERNAL_WEBHOOK_SECRET", "b" * 40)
    with pytest.raises(ValueError, match="credential|placeholder|DATABASE_URL"):
        Settings(
            _env_file=None, APP_ENV="production",
            DATABASE_URL="postgresql://workmate:placeholder@database.example:5432/workmate",
            FRONTEND_ORIGIN="https://workmate.example",
            AUTH_REVALIDATE_DB=True, AUTH_SESSION_STORE_ENABLED=True,
            AUTH_RATE_LIMIT_ENABLED=True, POSTGRES_RLS_REFERENCES=True,
        )


def test_deployer_preflights_idempotent_add_column_statements():
    target = deploy_owd_schema.add_column_if_missing_target(
        """ALTER TABLE SECURITY.departments
        ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE"""
    )

    assert target == ("SECURITY.departments", "is_active")
    assert target is not None

    cursor = MagicMock()
    cursor.fetchone.return_value = (1,)
    assert deploy_owd_schema.column_exists(cursor, *target) is True
    sql, params = cursor.execute.call_args.args
    assert "INFORMATION_SCHEMA.COLUMNS" in sql
    assert params == ("SECURITY", "DEPARTMENTS", "IS_ACTIVE")
