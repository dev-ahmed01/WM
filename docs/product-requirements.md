# Product Requirements (v1)

Derived from the product brief and `docs/product-audit.md`. Priority: **P0** pilot-blocking, **P1** commercial, **P2** later.

## Principles
Grounded, never invented; deterministic workflows; tenant isolation enforced in DB; private inference default; honest status (no fake success); reuse existing subsystems.

## Functional requirements
| ID | Requirement | Pri | Status at audit |
|---|---|---|---|
| R-ORG-1 | Organisations, warehouses, departments, job profiles, supervisors; user scope | P0 | Missing |
| R-ORG-2 | Tenant-scoped data and RLS on all tenant tables | P0 | Partial |
| R-RBAC-1 | Admin/Manager/Employee with documented permission matrix and boundary tests | P0 | Partial |
| R-ONB-1 | Admin creates/invites employees, deactivates, recovery | P0 | Missing |
| R-KB-1 | Upload, extract, OCR, preview, categorise, version, publish/archive/supersede | P0 | Mostly present |
| R-KB-2 | Approval gate for critical SOP changes (manager) | P1 | Missing |
| R-KB-3 | "Test before publish" Q&A | P1 | Missing |
| R-SOP-1 | ≥85 labelled demo SOPs in standard structure, idempotent seed | P0 | Missing |
| R-AI-1 | Intent routing, scoped hybrid retrieval, citation validation, injection defence | P0 | Present, unmeasured |
| R-AI-2 | Hindi/Hinglish understanding; bilingual eval ≥200 cases | P0 | Missing |
| R-AI-3 | Safety-critical stop-work responses, no invented repair steps | P0 | Partially covered |
| R-VOICE-1 | EN/HI/Hinglish voice in/out, editable transcript, states | P1 | Present |
| R-ACT-1 | Typed, allowlisted assistant actions with confirmation, audit, idempotency | P1 | Partial |
| R-ESC-1 | Escalation → human reply → employee notified → gap → SOP amendment | P0 | Partial |
| R-ANA-1 | Defined metrics from persisted events; helpful/not-helpful; filters | P1 | Partial |
| R-ANA-2 | ROI estimator labelled as estimate | P2 | Missing |
| R-SEC-1 | Cross-tenant, privilege, IDOR tests | P0 | Partial |
| R-DEP-1 | Compose + VPS runbook, backup/restore, rollback | P1 | Largely present (staging) |

## Non-functional
Mobile-first employee UI; accessibility (large touch targets, contrast); graceful degradation when Ollama/speech/DB fail; no fake metrics.

## Release targets (to be measured, not assumed)
100% tenant-isolation/authorisation tests; 0 unsupported safety instructions; 100% deterministic transition tests; ≥95% citation validity; ≥90% grounded-correct on benchmark.

## Out of scope
Certification/compliance claims; replacing a WMS; employee performance scoring from chats.
