# RBAC Permission Matrix

Generated from `backend/tests/golden/rbac_matrix.json`, which `backend/tests/test_rbac_matrix.py` produces by calling
every API operation anonymously and with admin/manager/employee tokens. ✔ = the role reaches the handler; — = rejected
by the auth/role dependency (401/403). All 107 operations deny anonymous callers.

**What this proves:** each route's role guard exists and matches this table; a change fails CI until the golden file is
regenerated and reviewed (`UPDATE_RBAC_GOLDEN=1`), then run `python scripts/generate_rbac_doc.py`.

**What it does not prove:** that a permitted role only sees its own organization's data. That is tested separately:
`test_org_admin_postgres.py` (employee admin, escalations), `test_tenant_knowledge_isolation_postgres.py`
(Knowledge Studio and reference documents, in a scratch database), and database RLS for reference documents. Row-level
security does **not** yet cover workflows, conversations, work items, exceptions, handovers or knowledge gaps; those rely
on application-layer organization/department filters.

Notes: `GET /api/v1/escalations`, `GET /api/v1/knowledge-gaps` and similar org-scoped routes may show — for every role
here because the probe uses a fake identity with no organization and the handler fails closed (403
`ORG_NOT_CONFIGURED`). `POST /api/v1/work/integrations/webhooks/{source_id}` is authenticated by HMAC signature,
not user role. Managers are scoped to their own department; admins to their organization.

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
| `POST /api/v1/analytics/roi-estimate` | ✔ | ✔ | — |
| `GET /api/v1/analytics/sop-usage` | ✔ | ✔ | — |
| `GET /api/v1/analytics/summary` | ✔ | ✔ | — |
| `GET /api/v1/auth/me` | ✔ | ✔ | ✔ |
| `GET /api/v1/copilot/history` | ✔ | ✔ | ✔ |
| `GET /api/v1/copilot/history/{conversation_id}` | ✔ | ✔ | ✔ |
| `POST /api/v1/copilot/message` | ✔ | ✔ | ✔ |
| `GET /api/v1/copilot/session/{id}` | ✔ | ✔ | ✔ |
| `POST /api/v1/copilot/session/{id}/abandon` | ✔ | ✔ | ✔ |
| `POST /api/v1/copilot/session/{id}/advance` | ✔ | ✔ | ✔ |
| `POST /api/v1/copilot/session/{id}/pause` | ✔ | ✔ | ✔ |
| `POST /api/v1/copilot/session/{id}/resume` | ✔ | ✔ | ✔ |
| `GET /api/v1/escalations` | — | — | — |
| `POST /api/v1/escalations/{escalation_id}/resolve` | ✔ | ✔ | — |
| `GET /api/v1/handover` | ✔ | ✔ | ✔ |
| `POST /api/v1/handover` | ✔ | ✔ | ✔ |
| `POST /api/v1/handover/{handover_id}/claim` | ✔ | ✔ | — |
| `POST /api/v1/handover/{handover_id}/review` | ✔ | ✔ | — |
| `GET /api/v1/knowledge` | ✔ | — | — |
| `GET /api/v1/knowledge-gaps` | — | — | — |
| `GET /api/v1/knowledge-gaps/mine` | ✔ | ✔ | ✔ |
| `POST /api/v1/knowledge-gaps/{gap_id}/dismiss` | — | — | — |
| `POST /api/v1/knowledge-gaps/{gap_id}/draft` | ✔ | — | — |
| `POST /api/v1/knowledge-gaps/{gap_id}/reply` | ✔ | ✔ | — |
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
| `GET /api/v1/knowledge/submissions` | ✔ | — | — |
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
| `GET /api/v1/procedure/approvals` | — | ✔ | — |
| `POST /api/v1/procedure/approvals/uploads/{submission_id}` | — | ✔ | — |
| `POST /api/v1/procedure/approvals/{draft_id}` | — | ✔ | — |
| `GET /api/v1/procedure/drafts` | ✔ | — | — |
| `POST /api/v1/procedure/drafts/import` | ✔ | — | — |
| `GET /api/v1/procedure/drafts/{draft_id}` | ✔ | — | — |
| `PUT /api/v1/procedure/drafts/{draft_id}` | ✔ | — | — |
| `GET /api/v1/procedure/drafts/{draft_id}/compile-preview` | ✔ | — | — |
| `POST /api/v1/procedure/drafts/{draft_id}/publish` | ✔ | — | — |
| `POST /api/v1/procedure/drafts/{draft_id}/review` | ✔ | — | — |
| `GET /api/v1/procedure/drafts/{draft_id}/source` | ✔ | — | — |
| `GET /api/v1/work/exceptions` | ✔ | ✔ | — |
| `GET /api/v1/work/exceptions/mine` | ✔ | ✔ | ✔ |
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
