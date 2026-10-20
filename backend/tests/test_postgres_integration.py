"""Real PostgreSQL integration (dedicated CI service; no Snowflake credentials)."""
from __future__ import annotations

import os
import uuid

import psycopg
import pytest

from app.core.database import close_postgres_pool, get_postgres_connection, ping
from app.repositories.user_repository import UserRepository
from app.repositories.reference_document_repository import ReferenceDocumentRepository
from app.services.ingestion import IngestionService
from app.core.security import hash_password


@pytest.mark.live_integration
def test_postgres_schema_auth_source_storage_and_reference_approval():
    dsn = os.environ["DATABASE_URL"]
    dept = "test_" + uuid.uuid4().hex[:10]
    user = "user_" + uuid.uuid4().hex[:10]
    doc_id = uuid.uuid4().hex
    role = "role_" + uuid.uuid4().hex[:10]
    source_uri = None
    with psycopg.connect(dsn, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO security.departments (id,code,name) VALUES (%s,%s,%s)",
                (dept, dept.upper(), "Postgres integration"),
            )
            cur.execute(
                "INSERT INTO security.roles (id,name,permission_set) VALUES (%s,%s,%s::jsonb)",
                (role, "admin", "{}"),
            )
            cur.execute(
                "INSERT INTO security.users (id,email,hashed_password,department_id) VALUES (%s,%s,%s,%s)",
                (user, f"{user}@example.test", hash_password("development-test-only"), dept),
            )
            cur.execute(
                "INSERT INTO security.user_roles (user_id,role_id) VALUES (%s,%s)", (user, role)
            )
    try:
        assert ping()
        profile = UserRepository.get_user_by_email(f"{user}@example.test")
        assert profile is not None
        assert profile["department_id"] == dept and profile["role"] == "admin"
        data = b"Damaged cartons must be isolated and reported to the supervisor."
        source_uri = IngestionService.stage_reference_file(data, "receiving.txt", dept, doc_id)
        assert source_uri.startswith("pgobj:")
        with get_postgres_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT department_id, content FROM shared.source_objects WHERE id = %s",
                    (source_uri.split(":")[1],),
                )
                owner, stored = cur.fetchone()
                assert owner == dept and bytes(stored) == data
        registered = ReferenceDocumentRepository.save_draft(
            document_id=doc_id,
            department_id=dept,
            title="Damaged goods",
            filename="receiving.txt",
            file_type="txt",
            mime_type="text/plain",
            stage_uri=source_uri,
            raw=data,
            extracted_text=data.decode(),
            warnings=[],
            created_by=user,
        )
        assert registered["status"] == "DRAFT"
        assert not ReferenceDocumentRepository.search_approved("damaged carton", dept)
        assert ReferenceDocumentRepository.change_status(doc_id, dept, user, action="approve")
        found = ReferenceDocumentRepository.search_approved("damaged carton", dept)
        assert found and found[0]["document_id"] == doc_id
        assert not ReferenceDocumentRepository.search_approved("damaged carton", "other_department")
        assert ReferenceDocumentRepository.change_status(doc_id, dept, user, action="archive")
        assert not ReferenceDocumentRepository.search_approved("damaged carton", dept)
        assert IngestionService.remove_staged_files([source_uri]) == 1
        source_uri = None
    finally:
        close_postgres_pool()
        with psycopg.connect(dsn, autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM knowledge_studio.reference_chunks WHERE document_id = %s", (doc_id,))
                cur.execute("DELETE FROM knowledge_studio.reference_documents WHERE id = %s", (doc_id,))
                if source_uri:
                    cur.execute("DELETE FROM shared.source_objects WHERE id = %s", (source_uri.split(":")[1],))
                cur.execute("DELETE FROM security.user_roles WHERE user_id = %s", (user,))
                cur.execute("DELETE FROM security.users WHERE id = %s", (user,))
                cur.execute("DELETE FROM security.roles WHERE id = %s", (role,))
                cur.execute("DELETE FROM security.departments WHERE id = %s", (dept,))


@pytest.mark.live_integration
def test_postgres_compiler_conversation_and_voice_lifecycle():
    """A real compiled SOP, chat message and voice row must commit on PG16."""
    from app.compiler.parser import OWDParser
    from app.compiler.validator import OWDValidator
    from app.compiler.compiler import OWDCompiler
    from app.compiler.loader import OWDLoader
    from app.repositories.conversation_repository import ConversationRepository
    from app.repositories.voice_repository import VoiceRepository
    from app.repositories.knowledge_repository import KnowledgeRepository

    dept = "flow_" + uuid.uuid4().hex[:10]
    user = "usr_" + uuid.uuid4().hex[:10]
    code = "SOPPG" + uuid.uuid4().hex[:9].upper()
    dsn = os.environ["DATABASE_URL"]
    with psycopg.connect(dsn, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO security.departments (id,code,name) VALUES (%s,%s,%s)",
                        (dept,dept.upper(),"Integration Warehouse"))
            cur.execute(
                "INSERT INTO security.users (id,email,hashed_password,department_id) VALUES (%s,%s,%s,%s)",
                (user,f"{user}@example.test",hash_password("test-password-not-for-users"),dept),
            )
    markdown = f"""# {code}: Goods Inspection

::state[STATE_START]{{type="ATOMIC_STEP" is_initial=true}}
## Inspect received cartons
Inspect the security seal before unloading the cartons.
- [ ] Inspect seal ::step[STEP_SEAL]
::transition{{to="STATE_END" condition="ALWAYS"}}

::state[STATE_END]{{type="END" is_terminal=true}}
## Goods inspected
Verified receiving checks finished.
"""
    document = OWDParser.parse(
        markdown_text=markdown, workflow_code=code,
        title="Goods Inspection", department_id=dept,
    )
    assert OWDValidator.validate(document).is_valid
    stage_uri = IngestionService.stage_file(
        markdown.encode(), "goods.md", f"{code}/v1",
        department_id=dept,
    )
    compiled = OWDCompiler.compile(
        document, stage_file_uri=stage_uri, source_filename="goods.md", user_id=user
    )
    loaded = OWDLoader.load(compiled)
    assert loaded.success
    assert KnowledgeRepository.get_published_version(loaded.workflow_id) is not None
    conversation_id = ConversationRepository.get_or_create_session(user, dept)
    message_id = ConversationRepository.persist_message(
        conversation_id, sender="ai", content="Inspect the security seal.",
        retrieved_state_ids=[], citations=[], confidence_score=0.95
    )
    assert ConversationRepository.belongs_to_user(conversation_id, user)
    voice_id = VoiceRepository.persist_interaction(
        conversation_id=conversation_id,
        response_message_id=message_id,
        user_id=user,
        original_language="hi", translated_language="en",
        original_transcript="सील की जांच", translated_transcript="Check the seal",
        response_text="Inspect the security seal.",
        transcription_confidence=0.88, transcription_ms=100,
        translation_ms=20, synthesis_ms=0, audio_id="audio_live_smoke",
        success=True,
    )
    assert voice_id.startswith("voice_")
    assert VoiceRepository.audio_belongs_to_user("audio_live_smoke", user)
    assert not VoiceRepository.audio_belongs_to_user("audio_live_smoke", "other_user")
    assert VoiceRepository.get_synthesis_source(message_id, user)["language"] == "hi"


@pytest.mark.live_integration
def test_postgres_workflow_progress_is_atomic_and_replay_safe():
    """The production session repository must enforce one recorded step per transition."""
    from app.repositories.conversation_repository import ConversationRepository
    from app.repositories.workflow_session_repository import WorkflowSessionRepository
    from app.exceptions.custom_exceptions import DatabaseException

    suffix = uuid.uuid4().hex[:11]
    dept, user, workflow = f"voice_{suffix}", f"user_{suffix}", f"wf_{suffix}"
    version, initial, terminal, step = (f"ver_{suffix}", f"st_a_{suffix}",
                                         f"st_b_{suffix}", f"step_{suffix}")
    with psycopg.connect(os.environ["DATABASE_URL"], autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO security.departments (id,code,name) VALUES (%s,%s,%s)",
                        (dept, dept.upper(), "Voice safety test"))
            cur.execute("""INSERT INTO security.users (id,email,hashed_password,department_id)
                        VALUES (%s,%s,%s,%s)""",
                        (user, f"{user}@example.test", hash_password("dev-only-test"), dept))
            cur.execute("""INSERT INTO knowledge_studio.workflows
                        (id,workflow_code,title,department_id,category,created_by)
                        VALUES (%s,%s,%s,%s,%s,%s)""",
                        (workflow, f"SOP_{suffix.upper()}", "Receive Goods", dept, "receiving", user))
            cur.execute("""INSERT INTO knowledge_studio.workflow_versions
                        (id,workflow_id,version_number,stage_file_uri,ast_hash,status)
                        VALUES (%s,%s,1,'pgobj:smoke','testhash','published')""",
                        (version, workflow))
            for id_, key, kind, ordinal in [
                (initial, "START", "ATOMIC_STEP", 0), (terminal, "END", "END", 1)
            ]:
                cur.execute("""INSERT INTO knowledge_studio.workflow_states
                            (id,workflow_version_id,state_key,state_type,title,
                             is_initial,is_terminal,ordinal_index)
                            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
                            (id_, version, key, kind, key, id_ == initial, id_ == terminal, ordinal))
            cur.execute("""INSERT INTO knowledge_studio.workflow_steps
                        (id,state_id,step_code,instruction,expected_output_type,ordinal_index)
                        VALUES (%s,%s,%s,%s,'CONFIRMATION',0)""",
                        (step, initial, "CONFIRM_SEAL", "Confirm undamaged seal"))
    conv = ConversationRepository.get_or_create_session(user, dept)
    session_id = WorkflowSessionRepository.create(conv, version, initial, user, {})
    state = WorkflowSessionRepository.get_active_by_conversation(conv)
    assert state["id"] == session_id and state["current_state_id"] == initial
    assert WorkflowSessionRepository.apply_progress(
        session_id, initial, state["updated_at"],
        {"verified_by": "explicit-user-confirmation"}, step_id=step,
        next_state_id=terminal, new_status="completed",
    )
    with pytest.raises(DatabaseException, match="concurrently|no longer active"):
        WorkflowSessionRepository.apply_progress(
            session_id, initial, state["updated_at"], {}, step_id=step,
            next_state_id=terminal, new_status="completed",
        )
    with get_postgres_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""SELECT current_state_id, previous_state_id, status
                        FROM workmate_copilot.workflow_sessions WHERE id=%s""", (session_id,))
            assert cur.fetchone() == (terminal, initial, "completed")
            cur.execute("""SELECT count(*) FROM workmate_copilot.workflow_step_executions
                        WHERE session_id=%s""", (session_id,))
            assert cur.fetchone() == (1,)
            cur.execute(
                """SELECT count(*) FROM shared.audit_logs
                   WHERE user_id=%s AND action='WORKFLOW_PROGRESS' AND resource LIKE %s""",
                (user, f"session:{session_id}:%"),
            )
            assert cur.fetchone() == (1,)
    assert WorkflowSessionRepository.get_active_by_conversation(conv) is None
