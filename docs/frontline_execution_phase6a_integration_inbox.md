# Phase 6A — WMS/ERP integration intake (controlled adapter contract)

## What is real
- A department manager submits a bounded, normalized WMS/ERP task event through the authenticated WorkMate API or the minimal **Integration inbox**.
- Source formats: `custom_wms`, `sap`, `oracle`, and `odoo`. These are **source schema labels**, not live vendor connections. No credentials, network requests, outbound ERP writes or vendor SDKs are implied.
- Records are persisted in PostgreSQL. Unique keys `(department_id, source_system, external_event_id)` and `(department_id, source_system, external_work_id)` prevent duplicates. SHA-256 of canonical normalized content distinguishes exact retries from conflicting replays.
- The first authorized manager stages a record with status `pending`; no work task exists yet.
- An **independent active manager/admin**, not the submitter, accepts or rejects the record with a substantive note. Acceptance creates one **queued** work item in the caller's department, with an audited `integration_imported` event carrying source ID, event ID, reviewer ID and digest. The work is unbound: `workflow_version_id=NULL`, `execution_session_id=NULL`, and `status=queued`. A published SOP is linked separately by the existing procedure-binding review before any employee can execute.
- Rejected records remain retained. Exact idempotent replay is valid even after acceptance; modified content or a new event referencing the same source work ID produces HTTP 409. Atomic transactions and `ON CONFLICT DO NOTHING` make concurrent replays safe.
- Department-scoped row-level security restricts the inbox, while the JWT role gate rejects employees; server rechecks active manager and chosen employee roles. Raw external URLs, remote commands, work-status overrides and arbitrary workflow IDs are not accepted.

## Endpoints
`POST /api/v1/work/integrations/intake` — managers/admins only. Body:

```json
{
  "source_system": "custom_wms",
  "external_event_id": "receipt.received.4001",
  "external_work_id": "RECEIPT-4001",
  "title": "Review incoming cartons",
  "work_type": "receiving",
  "priority": "high",
  "instructions": "Cross-check received cartons against dock reference.",
  "assigned_to": null
}
```

The response includes `id`, `status:pending` or a previously stored status and `replayed`. No task is started.

`GET /api/v1/work/integrations/intake?limit=100` — department-only review queue.

`POST /api/v1/work/integrations/intake/{id}/decision` — separate reviewer; `{"decision":"accepted"|"rejected","decision_note":"reason at least 16 chars"}`. On acceptance returns `work_item_id` and status `accepted`.

## Verification
- Authenticated API tests exercise role separation, malicious/synthetic authority fields, opaque errors, and replay semantics.
- Live PostgreSQL tests exercise exact retry, payload mutation, unique work ID collision, separate review, RLS isolation, queued-only work and exactly one audit event.
- Real Playwright/Chromium against disposable PostgreSQL: manager stages in browser; admin accepts in browser; task is `queued`, not executable; retry gives same task; unauthorized employee/other department denied.
- Quality workflow applies all migrations twice, runs new integration tests alongside existing security, cases and execution tests.

## Pilot honesty and next steps
This is **not a connected SAP/Oracle/Odoo integration**. It is a hardened adapter contract, authenticated intake review UI and transactionally idempotent task bridge. Phase 6B should implement explicitly configured vendor-specific adapters with source-signed requests, secret rotation, replay windows, transport retry/dead-letter monitoring and schema versioning; Phase 6C adds outbound event delivery with acknowledgement and retry policy. Do not auto-connect a warehouse or claim site acceptance until real installation credentials, partner contracts and operator validation are available. The production pilot remains **NO_GO**.
