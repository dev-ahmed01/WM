# WorkMate AI — PostgreSQL cutover

This branch replaces the expired Snowflake runtime with a PostgreSQL 16 foundation. It does not recover data from a disabled Snowflake account.

## Local startup

1. Copy backend/.env.example to backend/.env, set JWT_SECRET (>=32 characters), INTERNAL_WEBHOOK_SECRET (>=16), and other non-database settings. Never commit the populated file.
2. Set POSTGRES_PASSWORD to a strong development secret in your environment. For a host-native FastAPI process, set DATABASE_URL=postgresql://workmate:<password>@localhost:5432/workmate. Docker Compose supplies its internal postgres URL automatically.
3. docker compose up --build -d postgres
4. docker compose run --rm backend python scripts/migrate_postgres.py (or let the backend startup apply the baseline). The migration runner applies all numbered backend/migrations/postgres SQL files transactionally; rerunning is safe.
5. Provision an admin with explicit environment variables: BOOTSTRAP_ADMIN_EMAIL, BOOTSTRAP_ADMIN_PASSWORD (minimum 16 characters), BOOTSTRAP_DEPARTMENT_ID and BOOTSTRAP_DEPARTMENT_NAME. Run PYTHONPATH=backend python scripts/bootstrap_postgres.py in the configured app environment. Do not store the password in the repository.
6. docker compose up --build. Backend health is at http://localhost:8000/health; the frontend is at http://localhost:3000.

## Data compatibility

- Workflows, versions, graph nodes, execution sessions, audit events, conversations, voice interactions and approved reference documents are represented in native PostgreSQL schemas.
- Uploaded source bytes are in shared.source_objects as bounded BYTEA records, indexed by scoped object IDs; the source URI format is pgobj:<opaque-id>. The 25 MB document cap remains.
- Existing historical Snowflake stage URIs cannot be dereferenced. To reuse old data, obtain an export, transform and reingest under explicit reviewer supervision. If the account is inaccessible, seed fresh users and reupload documents instead.
- Old internal function names get_snowflake_connection and ping_snowflake_connection temporarily alias PostgreSQL. They never contact Snowflake. Refactor names in remaining repositories before final release.
- PostgreSQL 16 supports SQL MERGE used by the deterministic OWD loader. Snowflake VARIANT data maps to JSONB, and analytics views use native PostgreSQL aggregates.

## Security and production limitations

- The local Compose password fallback is for development only. APP_ENV=production rejects the built-in development DATABASE_URL; set a secret-managed PostgreSQL DATABASE_URL before production deployment.
- Use a limited application database role rather than the PostgreSQL schema owner, TLS in transit for a remote database, backups, retained audit logs, and a restore drill.
- Authenticated department checks are enforced by the repository/API; the new schema does not yet implement FORCE row-level security, so do not expose arbitrary database access to untrusted users.
- Source objects and vectors share PostgreSQL; consider object storage and pgvector with auditable approval revocation when scale requires it.
- The migration is forward-only for new records and has not been verified against any old Snowflake production export.
- CI runs PostgreSQL schema application twice and real integrations for auth/reference lifecycle and compiled SOP/conversation/voice data, plus existing focused backend regression and frontend build.
- Full system browser E2E and production traffic/load tests remain separate release gates.

## Voice action safety during PostgreSQL cutover

The existing Faster-Whisper/Piper pipeline is preserved. A high-confidence
informational utterance outside an active workflow may still receive a response.
However, spoken completion/confirmation commands, any speech during an active
or paused workflow, and low-confidence transcripts are never treated as
authoritative state mutations. The voice endpoint returns HTTP 409 with a
transcript for editing; the frontend places the translated text in the
composer for explicit Send. These 409 attempts are recorded as unexecuted
voice interactions in PostgreSQL for audit.

The 0.80 confidence cutoff is a conservative control threshold, NOT a measured
Hindi/Hinglish error-rate guarantee. Held-out bilingual audio benchmarks and
noise evaluations are still required before claiming voice reliability.

## CI integration run

Use the GitHub Actions WorkMate quality gates pipeline. Locally, with a disposable DATABASE_URL:
  WORKMATE_RUN_LIVE_TESTS=1 PYTHONPATH=backend python -m pytest -q backend/tests/test_postgres_integration.py

Do not set WORKMATE_RUN_LIVE_TESTS=1 against a non-disposable database; the tests insert synthetic rows.