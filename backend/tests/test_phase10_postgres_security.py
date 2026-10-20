"""Real PostgreSQL Phase 10 RLS, refresh revocation, replay and throttling gates."""
from __future__ import annotations
import uuid
from datetime import datetime, timezone
import psycopg
import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.database import close_postgres_pool
from app.core.security import decode_token, hash_password
from app.main import app
from app.repositories.reference_document_repository import ReferenceDocumentRepository
from app.repositories.session_security_repository import SessionSecurityRepository


@pytest.mark.live_integration
def test_pg_reference_reader_role_cannot_cross_departments(monkeypatch):
    suffix = uuid.uuid4().hex[:10]
    dept_a, dept_b = f"rlsa_{suffix}", f"rlsb_{suffix}"
    user_a, user_b = f"u_{suffix}_a", f"u_{suffix}_b"
    ids = [uuid.uuid4().hex for _ in range(2)]
    with psycopg.connect(settings.DATABASE_URL, autocommit=True) as conn:
        with conn.cursor() as cur:
            for dept, user in [(dept_a,user_a),(dept_b,user_b)]:
                cur.execute("INSERT INTO security.departments (id,code,name) VALUES (%s,%s,%s)",
                            (dept,dept.upper(),dept))
                cur.execute("""INSERT INTO security.users (id,email,hashed_password,department_id)
                               VALUES (%s,%s,%s,%s)""",
                            (user,f"{user}@example.test",hash_password("dev-test-secret"),dept))
    try:
        for doc, dept, user in [(ids[0],dept_a,user_a),(ids[1],dept_b,user_b)]:
            ReferenceDocumentRepository.save_draft(
                document_id=doc,department_id=dept,title="Security sealed cartons",
                filename="receiving.txt",file_type="txt",mime_type="text/plain",
                stage_uri="pgobj:synthetic",raw=b"Scan the security seal.",
                extracted_text="Inspect the security seal and quarantine damaged cartons.",
                warnings=[],created_by=user,
            )
        monkeypatch.setattr(settings, "POSTGRES_RLS_REFERENCES", True)
        visible = ReferenceDocumentRepository.list_documents(dept_a)
        assert [doc["id"] for doc in visible] == [ids[0]]
        assert ReferenceDocumentRepository.get_document(ids[1], dept_a) is None
        with psycopg.connect(settings.DATABASE_URL) as conn:
            with conn.cursor() as cur:
                cur.execute("BEGIN")
                cur.execute("SET LOCAL ROLE workmate_scoped_reader")
                # No scoped variable => zero rows even if the SQL itself is unscoped.
                cur.execute("SELECT count(*) FROM knowledge_studio.reference_documents WHERE id=ANY(%s)", (ids,))
                assert cur.fetchone() == (0,)
                cur.execute("SELECT set_config('workmate.department_id',%s,true)", (dept_a,))
                cur.execute("SELECT id FROM knowledge_studio.reference_documents WHERE id=ANY(%s)", (ids,))
                assert [row[0] for row in cur.fetchall()] == [ids[0]]
                cur.execute("SELECT count(*) FROM knowledge_studio.reference_chunks WHERE department_id=%s", (dept_b,))
                assert cur.fetchone() == (0,)
                cur.execute("ROLLBACK")
    finally:
        monkeypatch.setattr(settings, "POSTGRES_RLS_REFERENCES", False)
        with psycopg.connect(settings.DATABASE_URL,autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM knowledge_studio.reference_chunks WHERE document_id=ANY(%s)", (ids,))
                cur.execute("DELETE FROM knowledge_studio.reference_documents WHERE id=ANY(%s)", (ids,))
                cur.execute("DELETE FROM security.users WHERE id=ANY(%s)", ([user_a,user_b],))
                cur.execute("DELETE FROM security.departments WHERE id=ANY(%s)", ([dept_a,dept_b],))


@pytest.mark.live_integration
def test_pg_auth_refresh_replay_revoke_and_cross_worker_rate_limit(monkeypatch):
    suffix = uuid.uuid4().hex[:10]
    dept,user = f"auth_{suffix}", f"user_{suffix}"
    peer_user = f"peer_{suffix}"
    email = f"{user}@example.test"
    password = "Synthetic-Auth-Secret-2026!"
    monkeypatch.setattr(settings, "AUTH_SESSION_STORE_ENABLED", True)
    monkeypatch.setattr(settings, "AUTH_RATE_LIMIT_ENABLED", True)
    monkeypatch.setattr(settings, "AUTH_RATE_IP_BUCKET_ENABLED", False)
    monkeypatch.setattr(settings, "AUTH_RATE_MAX_ATTEMPTS", 4)
    with psycopg.connect(settings.DATABASE_URL,autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO security.departments (id,code,name) VALUES (%s,%s,%s)",
                        (dept,dept.upper(),dept))
            cur.execute("""INSERT INTO security.users (id,email,hashed_password,department_id)
                           VALUES (%s,%s,%s,%s)""", (user,email,hash_password(password),dept))
            cur.execute("""INSERT INTO security.users (id,email,hashed_password,department_id)
                           VALUES (%s,%s,%s,%s)""",
                        (peer_user,f"{peer_user}@example.test",hash_password(password),dept))
    try:
        with TestClient(app) as client:
            issued = client.post("/api/v1/auth/login",json={"email":email,"password":password})
            assert issued.status_code == 200, issued.text
            first = issued.json()["refresh_token"]
            first_claims = decode_token(first)
            assert SessionSecurityRepository.is_refresh_valid(first_claims["jti"],user)
            refreshed = client.post("/api/v1/auth/refresh",json={"refresh_token":first})
            assert refreshed.status_code == 200,refreshed.text
            second = refreshed.json()["refresh_token"]
            assert second and second != first
            replay = client.post("/api/v1/auth/refresh",json={"refresh_token":first})
            assert replay.status_code == 401 and replay.json()["detail"]["error_code"] == "AUTH_SESSION_REVOKED"
            revoked = client.post("/api/v1/auth/revoke",json={"refresh_token":second})
            assert revoked.status_code == 200
            assert client.post("/api/v1/auth/refresh",json={"refresh_token":second}).status_code == 401
            for _ in range(3):
                denied = client.post("/api/v1/auth/login",json={"email":email,"password":"incorrect"})
                assert denied.status_code == 401
            blocked = client.post("/api/v1/auth/login",json={"email":email,"password":password})
            assert blocked.status_code == 429
            # Same proxy/client IP must not lock out another employee.
            peer_login = client.post("/api/v1/auth/login", json={
                "email":f"{peer_user}@example.test", "password":password,
            })
            assert peer_login.status_code == 200, peer_login.text
    finally:
        close_postgres_pool()
        with psycopg.connect(settings.DATABASE_URL,autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM security.refresh_sessions WHERE user_id=ANY(%s)", ([user,peer_user],))
                cur.execute("DELETE FROM security.users WHERE id=ANY(%s)", ([user,peer_user],))
                cur.execute("DELETE FROM security.departments WHERE id=%s", (dept,))
