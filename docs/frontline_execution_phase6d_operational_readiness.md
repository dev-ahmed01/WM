# WorkMate Phase 6D — Integration Operational Assurance and Pilot Gate

## What is implemented

The Integration inbox now includes an **admin-only Integration readiness** desk populated from **committed, department-scoped PostgreSQL records** rather than mock counters. It exposes `GET /api/v1/work/integrations/operations/readiness`, a 24-hour observation window, and:

- Active/disabled registered sources; whether a *configured* inbound secret and outbound HTTPS target exist (never exposing values).
- Verified signed inbound deliveries over the last 24 hours; invalid/conflicting signed payloads; signed imports pending independent human review for more than 24 hours.
- Real outbound correlated acknowledgements received during the past 24 hours, outstanding events older than 60 minutes, dead-letter events and expired worker leases, and events waiting over 24 hours.
- Derived alert codes/counts per source and most recent immutable operator actions. Operator responses (acknowledged/remediation_logged) are **audit entries, NOT alert suppression**, workflow release, ERP receipt creation or independent signoff.
- A fail-closed `decision: "NO_GO"` regardless of technical configuration. When no connectors exist, `operational_status: not_configured`. When problems exist, `needs_attention`. Even with all configured technical checks clear, `configuration_preflight_clear_unverified` explicitly does **NOT** indicate a production pilot may launch.

A separate **admin-only** `POST /api/v1/work/integrations/operations/actions` accepts only source ID, known issue code, response classification and a substantive 16–1000 character note; the server derives department and actor from revalidated authentication. Actions are append-only in migration `017_integration_operations.sql` and scoped with Postgres RLS. There is no `set_operational_health=pass`, `clear_alerts`, `advance_sop` or `go_live` endpoint.

### Pilot release evidence

`scripts/pilot_release_gate.py` now requires an explicit boolean `bidirectional_integrations_in_scope` to avoid silently ignoring connector field evidence. The checked-in `deploy/pilot/evidence.template.json` sets this to **true** and all six integration field checks to **false**. If integration is in scope, independent release owners must provide actual evidence for:

1. `integration_ingress_tls_verified` — hosted TLS, authenticated source and abuse tests on the real endpoint
2. `integration_egress_firewall_verified` — private/loopback/link-local blocking for outbound DNS/IP routing, SSRF protection, TLS validation and exact destination allowlist in actual infrastructure
3. `integration_partner_ack_dedup_verified` — a live vendor order and correlated receipt, idempotency across retries, timeout/redirect/duplicate probes
4. `integration_secret_rotation_drilled` — actual ingress/outbound key changes, revocation and cutover tested without secret disclosure
5. `integration_dead_letter_recovery_drilled` — forced partner outage, dead-letter diagnosis, manual documented replay and recovery
6. `integration_external_security_review_signed_off` — independent deployment review with scope, dates, person and evidence artifacts.

If integration is out of scope, the release owner must explicitly say so and the deployed connectors/outbound worker must actually be disabled. Do not mark these true based on GitHub Actions or local mocks.

### On-call operations / rollback

1. Check `GET /api/v1/work/integrations/operations/readiness` using an active department administrator; record source ID, alert code, count, and the generated observation window. Raw keys, source request bodies and worker payloads do not belong in an incident ticket.
2. Inspect the connector signed intake ledger and ERP outbox under Integration inbox. Cross-check the partner's **correlated** ACK for the same stable event ID before claiming reconciliation.
3. For wrong/hostile inbound data or compromised signing credentials, **disable the affected source** in the admin UI. This denies new signed deliveries and outbound claim of that source. Rotate the secret in the protected deployment secret manager; re-enable only after source revalidation. Existing work/SOP holds stay intact.
4. For outbound delivery failures, leave the worker OFF if the destination or network egress is uncertain. Check tenant dead-letter records. Human recovery requires a 16+ character note, is limited to three cycles and does not change the original task. Never fabricate a partner receipt.
5. Confirm DB backup restore/rollback procedures and migration/runtime role separation in the hosted environment. Retain signed pilot artifacts in your approved private evidence store.
6. Confirm all independent pilot release gates are externally witnessed. Run:
   ```sh
   python scripts/pilot_release_gate.py --evidence deploy/pilot/evidence.template.json --strict
   ```
   This **must fail** with the checked-in template. A release owner can evaluate a separately reviewed evidence file, but there is no automatic permission to deploy from this command.
7. On unresolved critical issue, do **not** release held tasks. Disable connector, stop scheduled outbound worker, keep DB/evidence intact, and rollback only through the documented migration/deployment change-control process.

### Production limits

No production deployment, physical warehouse acceptance, genuine vendor subscription, actual egress firewall, deployed scheduler, hosted TLS checks, key-rotation drill, or independent approval has been performed here. A technical "preflight clear" never means a real pilot is safe. Health data is on-demand (not continuous monitoring): call the endpoint on an operator-owned schedule, e.g. from a privileged monitoring agent with explicit service authorization, and alert externally; no scheduled checks are secretly running. 24-hour metrics are **counts of database records**, not SLA percentages or measured warehouse productivity.

The pilot remains **NO_GO** without those field records.
