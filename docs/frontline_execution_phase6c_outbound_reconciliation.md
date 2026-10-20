# Phase 6C — Reviewed Work → Durable Outbound ERP Receipt

## Implemented contract

Only an **independently accepted signed inbound connector record** produces an outgoing reconciliation notice. Human acceptance, creation of one queued/unbound WorkMate task, the inbound review and event notification are in **one PostgreSQL transaction**. An unsigned/manual staged assignment is never routed to an ERP endpoint merely because its `source_system` label matches.

The outbox event is **`work_accepted`**. It is not SOP completion or physical goods reconciliation. Minimal JSON sent to the partner is:

```json
{
  "event_id":"out_<server-generated stable identifier>",
  "event_type":"work_accepted",
  "external_event_id":"receipt.received.4001",
  "external_work_id":"RECEIPT-4001",
  "source_system":"custom_wms",
  "work_item_id":"wrk_<server-generated ID>",
  "work_status":"queued"
}
```

No notes, personal information, evidence files, raw WMS source payload or sensitive workflow secrets are transmitted. The same **event_id and canonical JSON body** are reused across every retry.

## Network delivery

Outbound delivery is **OFF by default**. Production deployment must set:

- `WORKMATE_OUTBOUND_ENABLED=true`
- `WORKMATE_OUTBOUND_ALLOWED_HOSTS=receipt.partner.example` (exact, operator-controlled host names)
- `WORKMATE_OUTBOUND_TARGETS_JSON={"warehouse-east":{"url":"https://receipt.partner.example/workmate/events","secret":"<secret-manager-provisioned-separate-outbound-secret>"}}`
- Optional `WORKMATE_OUTBOUND_TIMEOUT_SECONDS=5`.

**Do not commit a real signing secret.** Register `warehouse-east` separately via the authenticated Phase6B admin connector screen, with a distinct inbound secret in `WORKMATE_CONNECTOR_SECRETS_JSON`. All destinations must be HTTPS, use a literal host in the allowlist, and cannot be IP literals, URLs with credentials or custom ports. HTTP redirects, environment proxies and unsafe response bodies are rejected. TLS verification remains enabled.

**Deployment must additionally enforce DNS-pinned/private-IP-blocking egress firewall rules, TLS termination and edge rate limits**. Static host validation alone does not prevent DNS rebinding: do not expose production egress until these safeguards and a vendor agreement are implemented.

To send a bounded batch from an operator-owned scheduled job:

```bash
PYTHONPATH=backend python backend/scripts/dispatch_integration_outbox.py --once --limit 10
```

The worker is not automatically started in a web request or on import. Operational scheduling and scaling are explicit infrastructure tasks, not a background service silently deployed by this PR.

Each outgoing request contains `Content-Type: application/json`, `X-WM-Outbox-Id`, `X-WM-Timestamp`, `X-WM-Signature`. The latter signs `HMAC-SHA256(outbound_secret, b"v1\\n" + timestamp + b"\\n" + event_id + b"\\n" + exact_raw_body)`. A partner must deduplicate by **event_id**, and answer with HTTP 2xx, JSON Content-Type and:

```json
{"event_id":"out_<same ID>","status":"accepted","receipt_id":"ERP-ACK-1001"}
```

An HTTP 200 without that exact correlated acknowledgement is **not delivered**; a timeout/redirect/5xx/invalid ACK results in a retry. This is **at-least-once delivery**, not exactly once, because a receiver may commit an event before the sender sees its acknowledgement. Partner deduplication is mandatory.

## Durable retry and human recovery

The PostgreSQL outbox uses `FOR UPDATE SKIP LOCKED`, a per-attempt lease token, 60-second lease expiry, and bounded backoff (30 s, 120 s, 300 s, 900 s). The fifth unsuccessful attempt becomes `dead`, with audit metadata and no task mutation. A worker crash can reclaim an expired lease and preserve the same event ID.

Admin-only `GET /api/v1/work/integrations/sources/{id}/outbox` lists per-department states without exposing destination secrets/payloads. `POST /api/v1/work/integrations/outbox/{event_id}/recover` with `{"justification":"An operational explanation with at least 16 characters."}` permits a documented retry of **dead** events, maximum three recovery cycles, only when the connector is active. Recovery never fabricates an ERP acknowledgement or advances the associated work item.

All outbox, attempt and recovery tables are department RLS scoped. No remote acknowledgement ever changes the original task, safety hold, workflow session or exception.

## Verification and limitations

CI includes unit/API tests for private-address/unsafe endpoint URLs, forged acknowledgements, redirects, transport failure and administrative access; real PostgreSQL tests for atomic source-review enqueue, five attempts, dead-letter recovery, lease token fencing, honest HTTPS mock ACK and cross-department RLS; and Playwright/Chromium tests of the outbox displayed after separate-manager approval.

**Not yet provided:** a connected vendor-certified SAP/Oracle/Odoo endpoint, field ERP receipt verification, production scheduler, network egress firewall, live mTLS, source-specific outbound mapping, completion-state outbound events, retention/monitoring alarms, or field operational acceptance. These require a real partner and infrastructure. Production pilot remains **NO_GO**.
