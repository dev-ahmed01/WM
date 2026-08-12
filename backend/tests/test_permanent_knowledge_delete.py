"""Transactional and staged-file safety tests for permanent SOP deletion."""

from unittest.mock import MagicMock, patch

import pytest

from app.exceptions import WorkMateException
from app.repositories.knowledge_repository import KnowledgeRepository
from app.services.ingestion import IngestionService


def _mock_connection():
    connection = MagicMock()
    cursor = MagicMock()
    cursor.rowcount = 1
    cursor.fetchall.return_value = [
        ("@RAW_OWD_STAGE/SOP_INB_101/v1/source.md",),
        ("@RAW_OWD_STAGE/SOP_INB_101/v2/source.md",),
    ]
    connection.cursor.return_value.__enter__.return_value = cursor
    manager = MagicMock()
    manager.__enter__.return_value = connection
    return manager, cursor


@patch("app.repositories.knowledge_repository.get_snowflake_connection")
def test_permanent_delete_is_transactional_and_scoped_to_one_workflow(mock_connection):
    manager, cursor = _mock_connection()
    mock_connection.return_value = manager

    result = KnowledgeRepository.permanently_delete_item("workflow-id")

    sql_calls = [str(call.args[0]) for call in cursor.execute.call_args_list]
    normalized_sql = " ".join(sql_calls).upper()
    assert "BEGIN" in sql_calls
    assert "COMMIT" in sql_calls
    assert "WORKMATE_COPILOT.WORKFLOW_SESSIONS" in normalized_sql
    assert "KNOWLEDGE_STUDIO.WORKFLOW_AI_CONVERSATION" in normalized_sql
    assert "KNOWLEDGE_STUDIO.WORKFLOW_ROLE_PERMISSIONS" in normalized_sql
    assert "DELETE FROM KNOWLEDGE_STUDIO.WORKFLOWS WHERE ID = %S" in normalized_sql
    assert "DELETE FROM WORKMATE_COPILOT.CONVERSATIONS" not in normalized_sql
    assert "DELETE FROM WORKMATE_COPILOT.CONVERSATION_MESSAGES" not in normalized_sql
    assert result["deleted_counts"]["workflows"] == 1
    assert len(result["stage_file_uris"]) == 2


@patch("app.repositories.knowledge_repository.get_snowflake_connection")
def test_permanent_delete_rolls_back_when_a_child_delete_fails(mock_connection):
    manager, cursor = _mock_connection()
    mock_connection.return_value = manager

    def execute(statement, params=None):
        if "workflow_states WHERE" in statement:
            raise RuntimeError("database failure")
        return cursor

    cursor.execute.side_effect = execute

    with pytest.raises(WorkMateException):
        KnowledgeRepository.permanently_delete_item("workflow-id")

    cursor.execute.assert_any_call("ROLLBACK")
    assert not any(call.args[0] == "COMMIT" for call in cursor.execute.call_args_list)


@patch("app.services.ingestion.get_snowflake_connection")
def test_staged_file_cleanup_accepts_only_exact_non_root_paths(mock_connection):
    manager, cursor = _mock_connection()
    cursor.fetchall.return_value = [("source.md", "removed")]
    mock_connection.return_value = manager

    removed = IngestionService.remove_staged_files(
        ["@RAW_OWD_STAGE/SOP_INB_101/v1/source.md"]
    )

    assert removed == 1
    cursor.execute.assert_called_once_with(
        "REMOVE @RAW_OWD_STAGE/SOP_INB_101/v1/source.md"
    )

    with pytest.raises(WorkMateException):
        IngestionService.remove_staged_files(["@RAW_OWD_STAGE"])
