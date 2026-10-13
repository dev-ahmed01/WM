# WorkMate — Phase 9 release acceptance

## Current release candidate architecture

WorkMate's browser no longer stores bearer or refresh tokens in JavaScript-accessible localStorage. `/api/session/login` verifies credentials with the existing PostgreSQL-backed FastAPI auth service and sets HttpOnly, SameSite=Strict cookies. `/api/session/me` revalidates a live account and returns only profile metadata. `/api/backend/[...path]` sends browser requests to a **fixed backend address** and forwards credentials only on the server. `/api/session/logout` expires both cookies.

All state-changing same-origin proxy and session routes enforce an Origin/Referer check. Cookies are `Secure` in production; only CI's explicitly flagged HTTP loopback environment may opt out. CSRF is not delegated to localStorage or bearer scripts. The proxy is not a general URL fetcher and does not accept arbitrary upstream hosts or forwarded cookies.

### Production deployment contract

- `APP_ENV=production` on FastAPI and `AUTH_REVALIDATE_DB=true` so stale role/department/disabled user JWTs are rejected.
- `WORKMATE_INTERNAL_API_URL=https://internal-api.example.com/api/v1` on the **Next.js server** only, never `NEXT_PUBLIC_*`. The internal API should not be exposed as a second browser endpoint.
- HTTPS with HttpOnly Secure cookies, trusted host routing, explicit allowed frontend origin, strong secrets, a protected Postgres connection, network filtering, and no test fixtures.
- Runtime access and refresh tokens are held in protected cookies. Refresh remains bounded by upstream FastAPI revocation/account checks; logout clears browser tokens but does not yet revoke stolen server-side refresh tokens in a centralized revocation table.
- Dedicated per-route rate limiting, brute-force controls and a complete account/session revocation registry remain production tasks; do not publish as broadly hardened authentication until tested.

## Durable reference approval

The reference status change and reviewer-signed audit action use a single PostgreSQL transaction with explicit BEGIN/COMMIT and ROLLBACK. Failed audit inserts cause approval/archival rollback. The generic middleware audit is an additional diagnostic log and not a substitute for this transactional record. Other critical workflows need similar transactional audit review before live regulated usage.

## Verified acceptance gates in CI

1. Full backend Python focused regression tests plus real PostgreSQL integration for auth/reference + OWD workflow/voice/optimistic progress.
2. Real Chromium → Next.js → FastAPI → PostgreSQL browser flow for admin login/upload/draft approval, employee scoped search, cross-department denial, and archive removal.
3. Browser asserts HttpOnly cookies are present, browser JS has no bearer or refresh tokens, and cross-origin writes fail CSRF validation.
4. `pg_dump` and `pg_restore` to a separate disposable database, with source-content SHA-256 and owner validation. This is a smoke test of logical recovery; it **does not** replace off-site backup, encrypted storage, PostgreSQL PITR or disaster recovery testing.
5. Frontend typecheck/production build; OCR English/Hindi language provisioning and a real English OCR smoke test. Genuine Hindi/Hinglish audio scoring remains pending.

## Remaining blockers before production claim

- Real TLS deployment smoke on the final target host and auth cookie security headers.
- PostgreSQL independent row-level security / low-privilege app role design. Current application checks are tested but the database owner could bypass them.
- Consistent transactional audit for **all** workflow-state and file-deletion mutations, including retry/outbox policies.
- Distributed auth session revocation/logout across all browser sessions, rate-limiting and lockout safeguards.
- Hosted PostgreSQL backup retention, WAL/PITR and an operator-executed recovery drill.
- Concurrency/load testing with a real embedding model and large departmental knowledge corpus.
- Independently labeled English, Hindi and Hinglish speech evaluation and reviewer sign-off.
- Approved security review and a merge of the stacked PR series, followed by CI on main.

## Integration sequence

Review and verify changes in PRs #11 through #19 in parent-to-child order. Each PR targets the previous feature branch. Do not deploy an unmerged individual PR as if it contained the entire tested release. Merge eligible PRs sequentially with required checks; after merging to main, run both full CI workflows against the main SHA, recheck runtime environment and hold a release gate meeting for outstanding risks.

## Test only

CI's browser test uses synthetic accounts in a disposable DB and sets `WORKMATE_BROWSER_SMOKE=1` to explicitly allow HTTP loopback testing. Never set this in a public release or against a remote database. Test token cookies do not appear in generated screenshots; screenshots on failure should not be retained beyond the configured short window.