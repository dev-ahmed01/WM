# RBAC Permission Matrix

Generated from `backend/tests/golden/rbac_matrix.json`, which is produced by actually calling every API operation
anonymously and with admin/manager/employee tokens (`backend/tests/test_rbac_matrix.py`). ✔ = the role reaches the
handler; — = rejected by the auth/role dependency (401/403). All 99 operations deny anonymous callers.

**What this proves:** each route's role guard exists and matches this table; changes fail CI until the golden file is
regenerated and reviewed (`UPDATE_RBAC_GOLDEN=1`).
**What it does not prove:** that a permitted role only sees its own organization/department data. That is tested
separately (`backend/tests/test_org_admin_postgres.py`: cross-organization employee admin, escalation scope) and, for
reference knowledge, by database RLS (`test_phase10_postgres_security.py`). Row-level security does **not** yet cover
workflows, conversations, work items, exceptions or handovers; those rely on application-layer department filters
(see `docs/product-audit.md`). Job-profile and manager warehouse scoping are modelled in the schema but not yet
enforced by most routes.

> Notes: `GET /api/v1/escalations` shows — for every role only because the probe uses a fake identity with no organization and the handler fails closed (403 `ORG_NOT_CONFIGURED`); real admins (whole organization) and managers (own department) are allowed. `POST /api/v1/work/integrations/webhooks/{source_id}` is authenticated by HMAC signature, not user role.

| Operation | Admin | Manager | Employee |
|---|---|---|---|
| `GET /api/v1/admin/employees` | ✔ | — | — |
| `POST /api/v1/admin/employees` | ✔ | — | — |
| `PATCH /api/v1/admin/employees/{employee_id}` | ✔ | — | — |
| `POST /api/v1/admin/employees/{employee_id}/recovery-token` | ✔ | — | — |
| `POST /api/v1/admin/employees/{employee_id}/status` | ✔ | — | — |
| `GET /api/v1/admin/org` | ✔ | — | — |
| `GET /api/v1/analytics/confidence-trends` | ✔ | ✔ | — |
| `GET /api/v1/analytics/confusing-procedures` | ✔ | ✔ | — |
| `GET /api/v1/analytics/department-adoption` | ✔ | ✔ | — |
| `GET /api/v1/analytics/escalations` | ✔ | ✔ | — |
| `GET /api/v1/analytics/faqs` | ✔ | ✔ | — |
| `GET /api/v1/analytics/sop-usage` | ✔ | ✔ | — |
| `GET /api/v1/auth/me` | ✔ | ✔ | ✔ |
| `GET /api/v1/copilot/history` | ✔ | ✔ | ✔ |
| `GET /api/v1/copilot/history/{conversation_id}` | ✔ | ✔ | ✔ |
| `POST /api/v1/copilot/message` | ✔ | ✔ | ✔ |
| `GET /api/v1/copilot/session/{id}` | ✔ | ✔ | ✔ |
| `POST /api/v1/copilot/session/{id}/abandon` | ✔ | ✔ | ✔ |
| `POST /api/v1/copilot/session/{id}/advance` | ✔ | ✔ | ✔ |
| `POST /api/v1/copilot/session/{id}/pause` | ✔ | ✔ | ✔ |
| `POST /api/v1/copilot/session/{id}/resume` | ✔ | ✔ | ✔ |
| `POST /api/v1/copilot/voice` | ✔ | ✔ | ✔ |
| `GET /api/v1/copilot/voice/audio/{audio_id}` | ✔ | ✔ | ✔ |
| `POST /api/v1/copilot/voice/speech` | ✔ | ✔ | ✔ |
| `POST /api/v1/copilot/voice/transcribe` | ✔ | ✔ | ✔ |
| `GET /api/v1/escalations` | ✔* | ✔* | — |
| `POST /api/v1/escalations/{escalation_id}/resolve` | ✔ | ✔ | — |
| `GET /api/v1/handover` | ✔ | ✔ | ✔ |
| `POST /api/v1/handover` | ✔ | ✔ | ✔ |
| `POST /api/v1/handover/{handover_id}/claim` | ✔ | ✔ | — |
| `POST /api/v1/handover/{handover_id}/review` | ✔ | ✔ | — |
| `GET /api/v1/knowledge` | ✔ | — | — |
| `GET /api/v1/knowledge/departments` | ✔ | — | — |
| `GET /api/v1/knowledge/ocr-status` | ✔ | — | — |
| `POST /api/v1/knowledge/preview` | ✔ | — | — |
| `GET /api/v1/knowledge/references` | ✔ | — | — |
| `POST /api/v1/knowledge/references` | ✔ | — | — |
| `GET /api/v1/knowledge/references/search` | ✔ | ✔ | ✔ |
| `GET /api/v1/knowledge/references/{document_id}` | ✔ | — | — |
| `POST /api/v1/knowledge/references/{document_id}/approve` | ✔ | — | — |
| `POST /api/v1/knowledge/references/{document_id}/archive` | ✔ | — | — |
| `GET /api/v1/knowledge/references/{document_id}/content` | ✔ | — | — |
| `POST /api/v1/knowledge/upload` | ✔ | — | — |
| `DELETE /api/v1/knowledge/{id}` | ✔ | — | — |
| `GET /api/v1/knowledge/{id}` | ✔ | — | — |
| `PUT /api/v1/knowledge/{id}` | ✔ | — | — |
| `DELETE /api/v1/knowledge/{id}/permanent` | ✔ | — | — |
| `GET /api/v1/knowledge/{id}/status` | ✔ | — | — |
| `GET /api/v1/knowledge/{id}/versions` | ✔ | — | — |
| `GET /api/v1/pilot/config` | ✔ | ✔ | ✔ |
| `POST /api/v1/pilot/feedback` | ✔ | ✔ | ✔ |
| `GET /api/v1/pilot/summary` | ✔ | ✔ | — |
| `GET /api/v1/procedure/drafts` | ✔ | — | — |
| `POST /api/v1/procedure/drafts/import` | ✔ | — | — |
| `GET /api/v1/procedure/drafts/{draft_id}` | ✔ | — | — |
| `PUT /api/v1/procedure/drafts/{draft_id}` | ✔ | — | — |
| `GET /api/v1/procedure/drafts/{draft_id}/compile-preview` | ✔ | — | — |
| `POST /api/v1/procedure/drafts/{draft_id}/publish` | ✔ | — | — |
| `POST /api/v1/procedure/drafts/{draft_id}/review` | ✔ | — | — |
| `GET /api/v1/procedure/drafts/{draft_id}/source` | ✔ | — | — |
| `GET /api/v1/work/exceptions` | ✔ | ✔ | — |
| `GET /api/v1/work/exceptions/{case_id}` | ✔ | ✔ | — |
| `POST /api/v1/work/exceptions/{case_id}/action` | ✔ | ✔ | — |
| `POST /api/v1/work/exceptions/{case_id}/claim` | ✔ | ✔ | — |
| `POST /api/v1/work/exceptions/{case_id}/closure/evidence` | ✔ | ✔ | — |
| `POST /api/v1/work/exceptions/{case_id}/closure/site` | ✔ | — | — |
| `POST /api/v1/work/exceptions/{case_id}/corrective` | ✔ | ✔ | — |
| `POST /api/v1/work/exceptions/{case_id}/corrective/{request_id}/decision` | ✔ | — | — |
| `POST /api/v1/work/exceptions/{case_id}/handover` | ✔ | ✔ | ✔ |
| `POST /api/v1/work/exceptions/{case_id}/review` | ✔ | ✔ | — |
| `GET /api/v1/work/execution/procedures` | ✔ | ✔ | — |
| `GET /api/v1/work/execution/{work_id}` | ✔ | ✔ | ✔ |
| `POST /api/v1/work/execution/{work_id}/bind` | ✔ | ✔ | — |
| `POST /api/v1/work/execution/{work_id}/block` | ✔ | ✔ | ✔ |
| `POST /api/v1/work/execution/{work_id}/continue` | ✔ | ✔ | ✔ |
| `POST /api/v1/work/execution/{work_id}/decision` | ✔ | ✔ | ✔ |
| `POST /api/v1/work/execution/{work_id}/pause` | ✔ | ✔ | ✔ |
| `POST /api/v1/work/execution/{work_id}/resume` | ✔ | ✔ | ✔ |
| `POST /api/v1/work/execution/{work_id}/start` | ✔ | ✔ | ✔ |
| `POST /api/v1/work/execution/{work_id}/step` | ✔ | ✔ | ✔ |
| `GET /api/v1/work/execution/{work_id}/timeline` | ✔ | ✔ | ✔ |
| `POST /api/v1/work/guidance/{work_id}` | ✔ | ✔ | ✔ |
| `GET /api/v1/work/integrations/intake` | ✔ | ✔ | — |
| `POST /api/v1/work/integrations/intake` | ✔ | ✔ | — |
| `POST /api/v1/work/integrations/intake/{intake_id}/decision` | ✔ | ✔ | — |
| `POST /api/v1/work/integrations/operations/actions` | ✔ | — | — |
| `GET /api/v1/work/integrations/operations/readiness` | ✔ | — | — |
| `POST /api/v1/work/integrations/outbox/{event_id}/recover` | ✔ | — | — |
| `GET /api/v1/work/integrations/sources` | ✔ | — | — |
| `POST /api/v1/work/integrations/sources` | ✔ | — | — |
| `POST /api/v1/work/integrations/sources/{source_id}/control` | ✔ | — | — |
| `GET /api/v1/work/integrations/sources/{source_id}/deliveries` | ✔ | — | — |
| `GET /api/v1/work/integrations/sources/{source_id}/outbox` | ✔ | — | — |
| `POST /api/v1/work/integrations/webhooks/{source_id}` | — | — | — |
| `GET /api/v1/work/items` | ✔ | ✔ | ✔ |
| `POST /api/v1/work/items` | ✔ | ✔ | — |
| `GET /api/v1/work/items/assignees` | ✔ | ✔ | — |
| `GET /api/v1/work/items/{item_id}` | ✔ | ✔ | ✔ |
| `POST /api/v1/work/items/{item_id}/assign` | ✔ | ✔ | — |
