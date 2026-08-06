# Copilot Retrieval, Cortex, and RBAC Fix

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

## Security note

The uploaded archive contained real-looking credentials in `backend/.env` and
`backend/.env.example`. The returned archive excludes runtime `.env` files and
contains only sanitized placeholders in `.env.example`. Rotate any password or
secret that was previously committed or shared.
