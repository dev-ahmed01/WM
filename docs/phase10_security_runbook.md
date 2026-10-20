# WorkMate Phase 10 — PostgreSQL security deployment and acceptance

## Implemented security controls

1. Refresh JWTs contain a unique random `jti`; PostgreSQL stores only HMAC-SHA256(jti). With `AUTH_SESSION_STORE_ENABLED=true`, login persists a session, refresh atomically invalidates the old token and issues a fresh access+refresh pair, and `POST /auth/revoke` revokes the active refresh token. Next.js rotates its HttpOnly cookie on refresh, and attempts PostgreSQL revocation before reporting logout success. Logout is not global revocation of access JWTs that are still valid.
2. Login throttling is backed by PostgreSQL `security.auth_rate_windows` and atomically updated across workers. Account buckets are enabled by default, with configurable window and maximum attempts. Optional IP buckets are disabled unless `AUTH_RATE_IP_BUCKET_ENABLED=true`; behind a shared Next.js backend-for-frontend, `client.host` often identifies the shared proxy, and an IP bucket would lock out unrelated workers. Enable only after validating trusted forwarding and identifying real clients; configure edge/WAF IP limits separately. Untrusted X-Forwarded-For headers are never accepted by this code.
3. Migration 003 creates `workmate_scoped_reader` with SELECT-only rights on the governed reference library and source-object table. Its PostgreSQL RLS policies require `current_setting('workmate.department_id')` to match `department_id`. Application reference search uses `SET LOCAL ROLE` and a local tenant setting within a transaction. The role cannot read any protected rows when the tenant variable is missing, and a read scoped to one tenant cannot fetch another tenant's reference data even if its query omitted a department predicate.
4. Workflow step progress and session status changes write an audit record in the same PostgreSQL transaction as the state change; failed writes roll back both.

## Operator setup (not a public deployment checklist completion)

- Run migrations using a dedicated schema owner. The migration grants the new scoped role to the current migration role for local CI. In production grant `workmate_scoped_reader` to the *application login role* explicitly: `GRANT workmate_scoped_reader TO workmate_runtime;` issued by an authorized database owner. The runtime credential must NOT own tables, have `BYPASSRLS` or be a superuser.
- Grant only the non-scoped permissions genuinely required for auth, execution and administrative write paths. Do not expose an SQL console or allow arbitrary statements from users; tenant selection is trusted server-side JWT revalidation, not user input.
- Set `AUTH_REVALIDATE_DB=true`, `AUTH_SESSION_STORE_ENABLED=true`, `AUTH_RATE_LIMIT_ENABLED=true`, and `POSTGRES_RLS_REFERENCES=true`. Production configuration refuses startup without all four settings.
- `AUTH_RATE_MAX_ATTEMPTS` defaults to 10 per window; `AUTH_RATE_WINDOW_SECONDS` defaults to 900. Consider account lockout notifications and monitored rate-control outages.
- Continue to use secret-managed `DATABASE_URL` with TLS, distinct migration/runtime logins, backup/PITR and a tested restore plan. Rotate any credentials used for local development.

## Unfinished protection scope

- **RLS is currently scoped to the governed reference library and source objects.** Conversations, workflows, analytics, voice records and other tables remain protected by application checks, not complete independent row-level policies. Do not present this as end-to-end DB-enforced multi-tenancy.
- Existing session expiry and status are checked during refresh; access tokens may remain valid until expiry unless the account's role, department or status changes. Global access-token revocation and device/session management remain future tasks.
- The Next.js server coalesces simultaneous refresh attempts within one Node process for 2.5 seconds. Refresh races across distinct server replicas remain a release concern: configure sticky routing or implement cross-replica coordination before claiming seamless multi-region login. Old JWTs are still rejected by PostgreSQL on replay.
- Remaining sensitive actions beyond workflow progress/status and reference approval/archive need transactional audit or outbox verification.
- No system-wide rate limiting for every Copilot/voice/embedding endpoint, no hosted penetration test, and no realistic Hindi/Hinglish audio field benchmark were performed.
- Production DB role grants and external TLS infrastructure are not yet validated in a hosted environment.

## Test gates

Run `PYTHONPATH=backend WORKMATE_RUN_LIVE_TESTS=1 pytest -q backend/tests/test_phase10_postgres_security.py` only against the disposable PostgreSQL CI instance. It verifies role-scoped SQL/zero-row behavior, refresh one-time rotation, logout revocation, replay rejection and shared throttling. Browser CI tests same-origin HttpOnly sessions and the document lifecycle. Existing regression suites remain in CI.