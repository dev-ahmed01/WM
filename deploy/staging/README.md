# WorkMate AI — Phase 11 staging infrastructure

**Status: deployment configuration and disposable CI verification, not a live hosted deployment.** No cloud subscription or database has been created by this PR. Deploy only after choosing a host/plan and provisioning a managed PostgreSQL 16 database.

## Topology and cost discipline

Caddy terminates public HTTPS and routes to a private Next.js server. Next.js communicates with FastAPI via `WORKMATE_INTERNAL_API_URL` on the private Docker network. The API connects over TLS to an existing managed PostgreSQL 16 database. No database port, API port, Ollama endpoint, or voice services are published to the internet. Staging intentionally disables Ollama/chat-model generation and microphone inference, but retains deterministic workflow, governed references, OCR and the UI. A slim image avoids downloading unused translation/Piper model weights; this is *not* an AI/voice acceptance environment.

A one-shot `migrate` service applies versioned SQL with the owner credential and grants a previously created non-owner runtime login scoped DML policies. A separate API service receives **only** the runtime URL and refuses to start if it can own tables, alter schemas, bypass RLS or query protected references without a tenant scope.

The existing Vercel `workmate-ai` project was found in the account listing; it has not been changed or redeployed. Railway exposes a different project, so this staging package does not create a potentially billable new Railway service. You can keep Caddy/Next.js and FastAPI on a single small test server, or later split the UI into Vercel after backend/DB staging is verified. This is not a cloud-cost quote.

## Corrected staging network plan — Phase 7A

The original reference Compose topology attached both the migration job and API only to a Docker network marked `internal: true`. That prevents outbound connections to the separately managed PostgreSQL service and is not a functional remote-database staging deployment.

The corrected topology separates:

- `internal` (**internal: true**) for Next.js ↔ FastAPI ↔ Caddy, without public access to API or frontend ports;
- `database_egress` (outbound-capable bridge) for migration, API, and optional encrypted-backup jobs to reach the **operator-provisioned managed PostgreSQL hostname**;
- `public` for Caddy HTTPS ingress only. The frontend is **not** on the outbound network, and FastAPI is never published as a host port.

**Security dependency:** Docker's outbound bridge is NOT a network firewall. An operator must restrict backend/migrator/backup egress to the actual PostgreSQL destination at the host/VPC firewall, use `sslmode=verify-full`, prevent private-IP / DNS-rebinding egress for any future external callback, and verify TLS certificates. Backend ERP outbound is explicitly **disabled** in this staging profile, and no vendor callbacks are configured.

`python scripts/check_staging_topology.py` is a **static** check for network separation, role preflight, and default-off ERP integrations; CI also checks Compose parsing. Neither is proof that the managed database is reachable or that firewall/TLS policies exist on an actual server. On the real host, test the network with operator-owned throwaway credentials against the approved PostgreSQL endpoint **before** application startup.

The sample staging environment remains placeholder-only. Real passwords and TLS configuration must come from an external secrets manager, never be committed to GitHub. A successful staging stack is still **not** a production pilot approval.

## Prerequisites (operator-owned)

1. A staging host with Docker/Compose, an unused DNS name pointing to it, inbound TCP 80/443 (and UDP 443 if HTTP/3 is desired), and outbound access to a managed PostgreSQL 16 instance.
2. A **migration** login with schema-owner/DDL privileges and permission to grant table DML and set role policies. Some managed providers prohibit `CREATE ROLE` and require an administrator to create `workmate_scoped_reader` or run initial migrations.
3. A separate pre-created **runtime** login on the same host/database with `LOGIN`, `NOSUPERUSER`, `NOBYPASSRLS`, `NOCREATEDB`, `NOCREATEROLE`. It must not own tables. Initial grants and tenant policies are applied by `scripts/grant_pg_runtime.py` during the one-shot migration step.
4. A separately protected **backup** login that has read access to *all* data required by `pg_dump`, including RLS-protected rows. Arrange a read-only administrative backup facility with the database provider. Do not grant that login to the API service. Some providers require a managed backup/PITR facility rather than a BYPASSRLS account.
5. A strong JWT secret, internal webhook secret and age public encryption recipient. Keep corresponding age *private* recovery key offline and separate from the staging server.
6. A backup destination with space/retention controls. The included `backup` profile writes only encrypted `.dump.age` files, but **you must copy them off-host** and conduct restore drills.

## Deployment steps

From the repository root of the reviewed Phase 11 branch:

```bash
cp deploy/staging/.env.example deploy/staging/.env.staging
# Edit deploy/staging/.env.staging locally; never commit the real file.
docker compose --env-file deploy/staging/.env.staging -f deploy/staging/compose.yml config --quiet
docker compose --env-file deploy/staging/.env.staging -f deploy/staging/compose.yml up -d --build
```

The default startup order is: migrate/grants → restricted API preflight → private frontend → HTTPS ingress. Caddy obtains and renews TLS certificates only after DNS and ports are correctly configured. Verify from outside the host:

```bash
curl --fail --show-error --silent https://YOUR_STAGING_DOMAIN/login
```

Perform a sign-in, admin draft upload, approval, employee scoped search and archive in the real HTTPS browser. Validate that access/refresh cookies are HttpOnly/Secure, CSRF rejection works, and the API/DB are not publicly routable. Treat account creation as an explicit operator action; the seed scripts are for disposable development only and must **never** run against staging.

### Backup and restore

Perform an encrypted one-shot logical dump (explicit opt-in profile):

```bash
docker compose --env-file deploy/staging/.env.staging \
  -f deploy/staging/compose.yml --profile backup run --rm backup
```

Backups appear in `deploy/staging/backups` as `wm-*.dump.age` with owner-only access. For example, on a separately secured recovery machine:

```bash
age --decrypt --identity /secure/offline-recovery-key.txt --output restored.dump wm-YYYYMMDDTHHMMSSZ.dump.age
pg_restore --no-owner --no-acl --exit-on-error --dbname "$DISPOSABLE_RESTORE_DATABASE_URL" restored.dump
```

Keep recovery key and PostgreSQL credentials outside logs and source control. Check source-object SHA-256, row counts and role permissions after restore. Never run `pg_restore` against production or a live database. A host-only encrypted dump is **not** an offsite backup, PITR, high-availability or disaster-recovery guarantee.

## CI and release gates

`.github/workflows/staging-preflight.yml` validates the Compose topology and provisions disposable PostgreSQL owner/runtime logins. It tests that the runtime role cannot perform DDL, can write/read/approve/archive *within* a tenant, cannot read another tenant's references using raw SQL, and cannot read protected rows with no tenant context. It also validates that staging refuses a missing/identical schema-owner identity or disabled auth controls. Existing full backend and browser CI remain required.

Before declaring staging operational, complete a real hosted TLS smoke, store actual environment secrets with your hosting provider, validate provider backup retention/PITR, run a separate restore drill, and test hostname/certificate/cookie behavior. Do not merge the draft main release candidate solely because this CI passes.

## Known boundaries

RLS in this build covers the governed reference tables and source bytes; other operational tables still rely on application-level authorization. Backup jobs require operational scheduling and remote encrypted retention. Multi-replica refresh coordination remains unsupported. Without deployed AI models, staging cannot demonstrate full answer generation or Hindi/Hinglish voice accuracy. No historical data has been transferred from expired Snowflake.
