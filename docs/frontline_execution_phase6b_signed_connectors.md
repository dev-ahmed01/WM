# Phase 6B — signed inbound connector and delivery diagnostics

## Actual capability

- A department administrator pre-provisions a distinct **random 32+ character HMAC key** under a stable source ID in server-side `WORKMATE_CONNECTOR_SECRETS_JSON`. The key is NEVER submitted through the UI, stored in PostgreSQL, or returned through an API. Setup/enable fails closed if the key does not exist or is too short.
- Admin registers a source ID and normalized source system (`custom_wms`, `sap`, `oracle`, `odoo`). These describe a **schema contract** only. No first-party SAP/Oracle/Odoo event subscriptions are present.
- The caller sends a signed, bounded **POST to the FastAPI ingress** at `/api/v1/work/integrations/webhooks/{source_id}`, without an employee session or Next.js CSRF token. This route uses its OWN authentication (not public unauthenticated acceptance): source HMAC, clock skew, nonce, active source and active registering admin. The role-protected manager/admin dashboard continues to use the normal Next.js same-origin cookie/CSRF proxy.
- Signed **JSON schema** is exactly the normalized Phase 6A `IncomingWork` model. Department, review decision, work status, SOP link, work session, evidence, safety release and arbitrary data fields cannot come from the vendor.
- The backend enters `pending` intake with the configured source owner's departmental identity for accounting. A **separate active manager/admin** must approve the event before even a **queued unbound** task exists. It never starts, advances, or resumes SOP execution.

## Signature recipe (v1)

HTTP request headers: `X-WM-Timestamp` (Unix epoch seconds, exactly 10 ASCII digits), `X-WM-Nonce` (unique unpredictable 16–80 URL-safe characters), and `X-WM-Signature` (`v1=` followed by lowercase 64-character hexadecimal SHA-256 HMAC).

```python
import hashlib,hmac,time,secrets,json
secret=b"READ_FROM_YOUR_SECRET_MANAGER_NOT_GIT"
timestamp=str(int(time.time()))
nonce=secrets.token_urlsafe(24)
body=json.dumps({
    "source_system":"custom_wms",
    "external_event_id":"receiving.confirmed.1001",
    "external_work_id":"RECEIVE-1001",
    "title":"Inspect inbound cartons",
    "work_type":"receiving","priority":"high",
    "instructions":"Compare the dock manifest with recorded goods.",
    "assigned_to":None
},separators=(",",":")).encode()
canonical=b"v1\n"+timestamp.encode()+b"\n"+nonce.encode()+b"\n"+body
signature="v1="+hmac.new(secret,canonical,hashlib.sha256).hexdigest()
# POST body as *unchanged bytes*. Never JSON-reserialize after signing.
```

The server reads at most **16 KiB**, validates a signature using constant-time compare, checks the signing timestamp within the default **±300 s**, rejects missing/disabled/unregistered keys, and stores a permanent `(source_id,nonce)` uniqueness record to reject signature replay. This permanent nonce ledger should have a retention/archival design before high-volume rollout.

A **retry after connection loss must use a fresh nonce and timestamp** while retaining the original external event and business work IDs and canonical source work fields. The Phase 6A idempotency contract then returns the existing pending/accepted record; the same nonce always fails. Changed payloads or conflicting external business IDs are not queued.

### Delivery outcomes

| Status | Ingestion | Response | Human review |
|---|---|---|---|
| `staged` | Valid new signed task | 202 | Pending |
| `replayed` | Same previously staged source event, new nonce | 202 | Unchanged |
| `conflict` | Source event/business ID already used with different data | 409 | No new task |
| `invalid` | Signed payload not recognized or wrong registered source schema | 422 | No task |
| Invalid/missing signing key, stale clock, bad signature or disabled source | Fail before durable inbox write | 401 | No task |
| More than 16 KiB raw body | Rejected during streaming read | 413 | No task |

Only **authenticated, signed** input is represented by a delivery record. Invalid-signature attempts are denied without filling the application's database. Delivery records hold only SHA-256 content digest, generic status/reason, source ID, nonce uniqueness and timing; NO secret, raw message or attachment bytes are persisted. Admin-only delivery health surfaces counts, timestamps and failures with department PostgreSQL RLS. HTTP 503 means the connector's transaction was not confirmed; caller must use fresh nonce to retry.

### Administrative control APIs

- `POST /api/v1/work/integrations/sources`: admin with `{"id":"source-warehouse-east","source_system":"custom_wms"}` and preprovisioned key
- `GET /api/v1/work/integrations/sources`: department admin-only source status, totals, failures and last delivery
- `GET /api/v1/work/integrations/sources/{id}/deliveries`: admin-only bounded metadata history
- `POST /api/v1/work/integrations/sources/{id}/control`: admin with `{"enabled":false}` or `{"enabled":true}` for immediate ingress kill-switch
- `POST /api/v1/work/integrations/webhooks/{id}`: signed ingress, service authentication as described above

## Explicit limitations and next gates

This is a **self-hosted HMAC ingestion contract**, **not** certified SAP/Oracle/Odoo SDK integration or a vendor-triggered event subscription. It is not mTLS, enterprise SSO, commercial API signing compliance, automatic bidirectional ERP sync or field-qualified safety clearance. TLS termination, WAF/edge rate limiting, per-source secret-manager operations, secret rotation, transport retry, source field mapping, clock synchronization, high-volume retention and load tests are still required before exposing to real third-party traffic. The reference implementation intentionally has NO outbound ERP writes. Pilot remains **NO_GO** until actual vendor endpoint, real user/site signoffs and production infra acceptance.
