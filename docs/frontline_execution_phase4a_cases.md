# WorkMate Phase 4A — Task-linked supervisor exception management

## Delivered in this phase

An active worker assignment can be stopped intentionally for a reported problem, or automatically when the compiled SOP reaches a supervised exception outcome. In **the same PostgreSQL transaction** the system:
1. Sets the work item to \`blocked\`, and pauses the existing execution session.
2. Creates exactly one case linked to work item, department, original session, operator, published SOP state and decision (when present).
3. Writes ordered immutable incident and task events. Evidence already recorded by the worker remains in private storage and its hashes/metadata remain in the work timeline.

The manager **Task exceptions** desk is accessible from Control room and the sidebar. It shows severity, actual work title/state, reporter, assigned reviewer, the linked task and audit history. A supervisor can claim a case with an optimistic revision and separately record either a review or a follow-up request with a mandatory written note. A review and its corresponding work event commit atomically.

## Non-negotiable safety invariants

- **Review is not release.** A supervisor case's \`reviewed\` or \`follow_up_requested\` status does not change the work item's \`blocked\` state, unpause the session or bypass SOP guards.
- Exception cases cannot be created from queued, ready or already-completed work. Exactly one case per blocked work item.
- Ordinary workflow safe endings complete normally, with no exception case.
- A \`requires_supervisor_review\` outcome in a published SOP enters an \`ESCALATION\` state, hard-stops execution and creates a critical case.
- Explicit worker stop creates a high-priority case. The worker gets the case ID but cannot view the supervisor-only review notes or endpoint.
- The reporter cannot self-review. The initial claimant owns the review; revision checks reject races and repeated actions.
- All reads and writes are department scoped; PostgreSQL RLS independently verifies tenant visibility. Neither the UI nor client input can assign arbitrary departments.
- Case list/detail intentionally contains only task details and event metadata; raw private attachments remain under the existing evidence access controls.
- Shift handovers remain a separate governed channel; task-to-handover cross-linking is reserved for Phase 4B.

## Acceptance gates

- API tests: worker forbidden from manager-only case API; literal decision constraints; independent role scopes; conflict/not-found/private error paths.
- Real PostgreSQL test: case creation, uniqueness, owner claim, stale write denial, cannot review own report, follow-up state, immutable events, unchanged paused session/blocked work, RLS.
- Actual Chromium test: generated SOP→manager assignment→worker steps and required JPEG→exception decision→blocked task→manager case opened/claimed/reviewed→still blocked; confirm employee cannot access case API and outsider cannot access task.
- Full regression, Next.js typecheck/build, migrations applied twice and staging security checks must pass.
- Production rollout remains prohibited without actual safety review/operational acceptance evidence.

## Next phase

Phase 4B adds task-to-handover linking, supervisor containment and remediation records with separate approvals and explicit SOP re-entry policy (not an unrestricted resume), exception-aging analytics and audit export. We must measure time-to-owner and time-to-review using real event timestamps, not fabricated productivity metrics.

## Integration order

Phase 4A PR #32 stacks on the fully verified Phase 3B PR #31; behind that are Phase 3A #30, Phase 2 #29, Phase 1 #28 and the PostgreSQL foundation. Do not merge these directly into outdated main, skip review, or confuse a draft PR with a hosted production release.
