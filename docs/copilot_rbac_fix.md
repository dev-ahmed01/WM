# Copilot Retrieval, Cortex, and RBAC Fix

## Audit summary

| Area | Expected behaviour | Current implementation | Status | Required action |
|---|---|---|---|---|
| Cortex retrieval | Service search plus department/status filters | Configured Search Preview request and scoped lexical SQL fallback | Verified | Deploy and verify the service in the target account |
| Answer generation | Grounded `AI_COMPLETE` over authorized chunks | Prompt is assembled only from retrieval results; validation builds citations from those same results | Verified | Verify the configured model and grants live |
| RBAC | Canonical roles and JWT-derived department | Access tokens require role/department claims; route dependencies normalize roles | Verified | Seed real users/roles/departments |
| CORS/API | Explicit credentialed origins and `/api/v1` client base | Explicit configured/local origins; frontend base includes `/api/v1` | Verified | Set the production frontend origin |

`PROJECT_CONTEXT_V2.md` names `backend/app/utils/cortex_client.py`, but the
repository implementation uses `backend/app/integrations/cortex_client.py`.
The fix follows the imported, runtime implementation rather than recreating a
duplicate client. Obsolete ingestion-only summarize, extraction, and embedding
helpers were removed from that runtime client so Cortex remains a Copilot-time
dependency only.

## Root causes corrected

1. `CortexClient.search()` performed phrase-level SQL `LIKE` matching and then
   returned unrelated rows when there was no match. It now queries the Cortex
   Search service with department/status filters and falls back only to
   token-aware, relevance-ranked SQL.
2. `generate_response()` returned a hard-coded valve instruction. It now calls
   Snowflake `AI_COMPLETE` with the retrieved OWD content. If the account/model
   is unavailable, it returns an extractive answer from the top verified result.
3. Snowflake role names (`Admin`, `Supervisor`, `Employee`) did not match API
   roles (`admin`, `manager`, `employee`). Roles are now canonicalized and seed
   data uses the API vocabulary.
4. Refresh tokens could be accepted by generic authenticated dependencies.
   Protected routes now require `type=access`, role, and department claims.
5. The test-user seed omitted the required department `code` and used
   unqualified tables. The seed now matches `SECURITY` schema DDL.
6. Citation `step_number` could receive a UUID-like identifier. Retrieval now
   joins workflow states to return the numeric ordinal, while the response model
   safely accepts stable string identifiers if a future search source uses them.
7. Credentialed CORS included a wildcard origin. The wildcard was removed.

## Required Snowflake steps

Run `analytics/migrations/11_cortex_search_service.sql` with a role allowed to
create Cortex Search services. Then verify:

```sql
SHOW CORTEX SEARCH SERVICES
IN SCHEMA WORKMATE_AI.KNOWLEDGE_STUDIO;

SELECT AI_COMPLETE(
    'mistral-large2',
    'Reply with exactly: Cortex connection successful'
);
```

The backend Snowflake role needs Cortex privileges. An `ACCOUNTADMIN` can grant
the appropriate database role and service usage:

```sql
GRANT DATABASE ROLE SNOWFLAKE.CORTEX_USER TO ROLE <WORKMATE_BACKEND_ROLE>;

GRANT USAGE ON CORTEX SEARCH SERVICE
    WORKMATE_AI.KNOWLEDGE_STUDIO.WORKMATE_KNOWLEDGE_SEARCH
    TO ROLE <WORKMATE_BACKEND_ROLE>;
```

Publish legacy compiled workflow versions before production retrieval:

```sql
UPDATE WORKMATE_AI.KNOWLEDGE_STUDIO.WORKFLOW_VERSIONS
SET STATUS = 'published',
    PUBLISHED_AT = COALESCE(PUBLISHED_AT, CURRENT_TIMESTAMP())
WHERE ID = '<WORKFLOW_VERSION_ID>'
  AND LOWER(STATUS) = 'compiled';
```

Production configuration must use:

```env
COPILOT_ALLOWED_KNOWLEDGE_STATUSES=published
```

If an unpublished legacy workflow must be tested temporarily in local
development, `published,compiled` is supported, but it must not be used in
production.

After changing role assignments or role-name seed data, log out and log back in
so the browser receives a new access token with canonical claims.

## Verification performed

- Python source compilation succeeded.
- Focused authentication, RBAC, retrieval, validation, and Cortex tests passed.
- The Next.js production build completed successfully.
- Live Snowflake execution was not performed from the audit environment; the
  migration and privilege checks above remain deployment steps.

## Files changed in this correction set

- `backend/app/integrations/cortex_client.py`
- `backend/app/services/retrieval.py`
- `backend/app/api/v1/copilot.py`
- `backend/app/core/config.py`
- `backend/app/core/security.py`
- `backend/app/middleware/auth_middleware.py`
- `backend/app/middleware/rbac_middleware.py`
- `backend/app/main.py`
- `analytics/migrations/11_cortex_search_service.sql`
- `frontend/lib/api-client.ts`
- `frontend/.env.example`
- focused tests under `backend/tests/`

## Remaining limitations and live verification

Cortex Search and `AI_COMPLETE` require a live Snowflake account and cannot be
certified by mocked unit tests. After applying the migration and grants, issue
queries as users from two real departments and confirm that Search Preview
returns only the caller's department and configured lifecycle statuses. Confirm
that empty searches produce the grounded failure/escalation response and that
each returned citation ID exists in the search response passed to the model.

The relational deployment intentionally excludes the Cortex Search migration.
Apply `11_cortex_search_service.sql` separately with a Cortex-privileged role;
then run `SHOW CORTEX SEARCH SERVICES` and a scoped Search Preview query.

## Security note

The uploaded archive contained real-looking credentials in `backend/.env` and
`backend/.env.example`. The returned archive excludes runtime `.env` files and
contains only sanitized placeholders in `.env.example`. Rotate any password or
secret that was previously committed or shared.
