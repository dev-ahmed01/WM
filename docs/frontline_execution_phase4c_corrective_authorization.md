# WorkMate Phase 4C — independent corrective work authorization

## Goal
Make an incident actionable without allowing a supervisor to clear a blocked SOP or falsify an observed physical safety condition. Authorized corrective work is a **separate new task**, with its own source-backed published SOP and execution/evidence history.

## Workflow
1. Phase 4A/4B stop the original work, pause its session, preserve evidence and open a scoped incident.
2. Original case reviewer records a review, containment and remediation proposal (Phase 4B).
3. That reviewer proposes a corrective work plan with a named active employee, a specific department-published SOP version and a 20–1000-character verification scope. The plan is a durable pending, single-use request.
4. A **different** authenticated administrator considers the plan, records an independent decision note and approves or rejects it. The original reporter, reviewer, plan proposer and planned worker cannot be the approver.
5. Approval atomically inserts a **new**, high-priority **ready** work assignment bound to that published SOP version; records its created/bound events and the original case's approved audit events; links the new task to its request. Rejection records a decision and creates no task.
6. The assigned employee may start the new task via the existing Phase 2 guarded execution engine. Its session is new; the original session remains paused and original task remains blocked.

## Safety rules
- **Approval is not physical clearance**: it authorizes only separate verification work. No incident status is set to “resolved,” no original task is resumed, no source proof is independently certified, and no blocked state is bypassed.
- Corrective version must still be published in the same department, contain an actual initial ATOMIC_STEP with an instruction and a terminal END, and the assignee must still have an active employee role. This is rechecked *at approval*, not only at request.
- The owning reviewer can submit only after a completed case review plus documented containment and remediation. It is impossible to skip those prerequisites.
- A case can have only one pending/decided corrective request. The department-scoped case row is locked during proposal and approval; duplicate or stale submissions are rejected with conflict, backed by a unique database constraint.
- The two-person decision is enforced in the repository, not just the interface, and the API requires an administrator role; extra fields claiming release of a task or case are forbidden.
- The case request and task are tenant protected with PostgreSQL RLS, task-level role constraints and append-only events. Notes disclose no raw evidence bytes.
- Proposal, approval and creation of the corrective task are transactional per action; failures leave no half-approved task.
- Out-of-band QA and site-specific safety clearance remain required for any physical release, which is outside WorkMate 4C.

## Acceptance
- API tests ensure employees cannot propose/approve, managers cannot approve, and fabricated release fields are rejected.
- Real PostgreSQL tests cover independent reviewer, prerequisite sequence, wrong department/employee/SOP, duplicate replay, independent approval, assigned new ready task, new evidence session, unchanged original blocked task/session and independent RLS.
- Chromium acceptance: operator incident → owner containment/remediation → owner proposes selected published SOP and assignee → different admin approves → worker starts the new corrective task → original work remains blocked; prior Phase 1–4B regression journeys still pass.
- Migration 012 must apply twice; frontend typecheck/build, staging security and full integration gates must pass at exact HEAD. External pilot remains NO_GO without independent human/site signoff.

## Follow-on milestones
- Phase 4D: separately governed *case closure* only after corrective work has completed under the published SOP, human signoff has been recorded and proof has been reviewed; no automatic source task resumption.
- Phase 5: contextual role-aware grounded AI in executing work, validated Hindi/English/Hinglish voice and field hardware acceptance tests.

## Integration
PR #34 stacks on Phase 4B #33 -> Phase 4A #32 -> 3B #31 -> 3A #30 -> 2 #29 -> 1 #28 -> earlier PostgreSQL foundation. Do not merge directly into stale main; independent safety/pilot rollout remains NO_GO.
