# WorkMate AI — Phase 8 integration and production readiness

## What is verified automatically

- PostgreSQL 16 migrations applied twice to a disposable database without relying on Snowflake.
- FastAPI integration creates real accounts, signs in with password, uploads a reference source, confirms draft invisibility, approves, searches from the correct department, rejects a cross-department employee, archives the source and confirms immediate search revocation.
- The same real API check disables a user in PostgreSQL and proves the previously issued JWT is rejected with AUTH_STALE.
- PostgreSQL shared.audit_logs must contain persisted audit rows for reference create/approve/archive. The SQL is native PostgreSQL; no Snowflake UUID_STRING or CURRENT_TIMESTAMP() remains in that middleware.
- Real Chromium browser logs in as an admin and two employees, uploads a document through the Next.js interface, reviews/approves it and tests role isolation and archive revocation.
- Existing real PG tests continue to validate SOP compilation, voice records, and optimistic concurrency/replay protection.
- Production requires AUTH_REVALIDATE_DB=true, and failed account verification rejects protected requests instead of silently trusting an older JWT.
- GET /ready returns HTTP 503 when PostgreSQL is unreachable, while GET / is a lightweight process liveness endpoint. The API's PostgreSQL pool is closed on shutdown.
- Unexpected infrastructure errors are hidden from production HTTP responses instead of returning raw SQL connection messages.

## Explicit limits — do not advertise this PR as production launch

- Browser E2E is a disposable CI local-stack test. A separately hosted deployment, real TLS termination, SMTP/account recovery, multi-replica scale, workload benchmarking and external load balancer configuration are not yet verified.
- JWT tokens remain in the existing browser localStorage client. A future HttpOnly cookie/session + CSRF design should replace localStorage before broad deployment.
- PostgreSQL row-level security is not yet enforced independently of the application. Apply least-privilege roles and database isolation; a stolen high-privilege DB credential remains dangerous.
- The audit middleware writes after the endpoint response and logs failures; it cannot roll back a committed business mutation if its audit insert fails. For safety-critical workflow actions, use an audit/outbox write in the *same* database transaction.
- Browser credentials and documents are synthetic and disposable. Never seed browser fixtures in production.
- PostgreSQL backups, point-in-time recovery, restore drills, secrets management, network TLS and operator approval still need real deployed validation.
- Real independently labeled English/Hindi/Hinglish audio, multilingual word error rates and translation faithfulness remain unmeasured.
- Phases #11–#17 and this PR are stacked and unmerged. Confirm each parent passes, then merge in order before promoting deployment.

## Local smoke prerequisites

Set DATABASE_URL to local disposable PostgreSQL; run migrations. For the opt-in seed, use APP_ENV=dev, WORKMATE_BROWSER_SMOKE=1 and WORKMATE_E2E_PASSWORD with >=16 chars, then run PYTHONPATH=backend python backend/scripts/seed_browser_smoke.py. Never use an externally reachable DB in this procedure.

CI workflow .github/workflows/browser-smoke.yml brings up PostgreSQL, seeds disposable users, runs real FastAPI and Next.js and executes backend/e2e/browser_smoke.py with Chromium. It saves failure screenshots for diagnostics only.

## Operator acceptance before launch

1. Set production APP_ENV, AUTH_REVALIDATE_DB=true, secret-managed DATABASE_URL and JWT_SECRET, TLS-only public endpoints and explicit FRONTEND_ORIGIN.
2. Use limited database roles and verify no public database access. Rotate default passwords and configure strong backups.
3. Complete a real backup/restore drill with a new database and compare record counts and source byte hashes.
4. Verify account-disable, department reassignment, reference archive and role downgrade against a deployed multi-user stack.
5. Load-test concurrent reference search and workflow progress, instrument 5xx and p95 latency and ensure alarms are actionable.
6. Review the open PR stack and document user acceptance on the exact deployment commit.