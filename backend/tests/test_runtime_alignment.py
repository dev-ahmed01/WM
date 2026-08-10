"""Regression tests for Snowflake runtime schema alignment."""

from pathlib import Path
from unittest.mock import MagicMock, patch

from app.repositories.conversation_repository import ConversationRepository
from app.repositories.escalation_repository import EscalationRepository
from app.services.analytics_service import AnalyticsService
from app.middleware.audit_logger import _record_audit_entry_sync


def _mock_connection():
    connection = MagicMock()
    cursor = MagicMock()
    connection.cursor.return_value.__enter__.return_value = cursor
    manager = MagicMock()
    manager.__enter__.return_value = connection
    return manager, cursor


@patch("app.repositories.conversation_repository.get_snowflake_connection")
def test_conversation_creation_is_schema_qualified_and_persists_department(mock_connection):
    manager, cursor = _mock_connection()
    mock_connection.return_value = manager

    ConversationRepository.get_or_create_session("usr_1", "dept_ops")

    sql, params = cursor.execute.call_args.args
    assert "WORKMATE_COPILOT.conversations" in sql
    assert params[1] == "usr_1"
    assert params[2] == "dept_ops"


@patch("app.repositories.escalation_repository.get_snowflake_connection")
def test_escalation_insert_targets_runtime_table(mock_connection):
    manager, cursor = _mock_connection()
    mock_connection.return_value = manager

    EscalationRepository.create("msg_1", "low confidence")

    sql = cursor.execute.call_args.args[0]
    assert "WORKMATE_COPILOT.escalation_records" in sql


@patch("app.services.analytics_service.get_snowflake_connection")
def test_analytics_insert_targets_runtime_table(mock_connection):
    manager, cursor = _mock_connection()
    mock_connection.return_value = manager

    AnalyticsService.record_event("copilot.turn", conversation_message_id="msg_1")

    sql = cursor.execute.call_args.args[0]
    assert "INTELLIGENCE_HUB.analytics_events" in sql


def test_runtime_prerequisites_provision_stage_and_side_effect_tables():
    sql = Path("analytics/migrations/13_runtime_prerequisites.sql").read_text(encoding="utf-8")

    assert "CREATE STAGE IF NOT EXISTS KNOWLEDGE_STUDIO.RAW_OWD_STAGE" in sql
    assert "WORKMATE_COPILOT.escalation_records" in sql
    assert "CREATE TABLE IF NOT EXISTS INTELLIGENCE_HUB.analytics_events" in sql


@patch("app.middleware.audit_logger.get_db_cursor")
def test_audit_logger_targets_migration_backed_table_and_columns(mock_cursor):
    cursor = MagicMock()
    mock_cursor.return_value.__enter__.return_value = cursor
    _record_audit_entry_sync({
        "user_id": "usr_1",
        "role": "admin",
        "action": "POST /api/v1/knowledge/upload",
        "resource": "/api/v1/knowledge/upload",
        "ip_address": "127.0.0.1",
        "status_code": 200,
    })
    sql = cursor.execute.call_args.args[0]
    assert "SHARED.audit_logs" in sql
    assert "STATUS_CODE" in sql and "ROLE" in sql


def test_runtime_integrity_migration_provisions_analytics_views():
    sql = Path("analytics/migrations/14_runtime_integrity.sql").read_text(encoding="utf-8")
    assert "INTELLIGENCE_HUB.V_ANALYTICS_FAQS" in sql
    assert "INTELLIGENCE_HUB.V_ANALYTICS_CONFIDENCE_TRENDS" in sql
    assert "ADD COLUMN IF NOT EXISTS status_code" in sql
