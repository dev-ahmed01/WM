# WorkMate Phase 4B — Operational continuity and containment

## Goal
Make blocked SOP tasks survivable across shifts without inventing approvals, losing original evidence, or silently releasing safety holds.

## Delivered behavior
- **Case-bound shift transfer.** The person who raised a real blocked task can submit its next-shift action and context from the worker's work screen. The server retrieves the original paused workflow session, conversation, SOP state, actor and department from PostgreSQL; it does *not* accept an arbitrary conversation or department from browser input.
- **One linked handover per case.** A database UNIQUE constraint on \`shift_handovers.work_exception_id\` rejects duplicates, including simultaneous submissions. The handover is created in the existing shift-handover system (not a parallel queue), so existing manager claiming/review works unchanged.
- **Atomic session snapshot and audit.** The handover, handover submission event, case audit event and task event are saved together or all rolled back. Original task remains blocked. Original evidence and session remain intact.
- **Bidirectional traceability.** Manager case view links to shift-handover review; the shift review view links back to its task exception. RLS and existing role rules protect each surface.
- **Actual incident aging.** Case queue displays relative elapsed time since the server-saved creation timestamp, using IST for display and updating every minute. A longest-open indicator describes observed elapsed time, **not an invented SLA threshold**.
- **Append-only containment/remediation records.** The owning supervisor may append a mandatory factual note recording containment. A remediation proposal can only follow an existing containment record. Actions are revision-checked, appended to the case and task timeline, and never treated as independent verification.
- **No auto-resume.** Reviewed case, handover acknowledgment, containment record or remediation proposal cannot unpause the underlying workflow session or mark the work item completed. Safety-gated re-entry requires a separately designed and tested authorization policy.

## Security and review requirements
- Task reporter can initiate the linked shift handover, but cannot access supervisor-only case details or claim, review, contain or propose a plan as the reviewer.
- A same-department but different employee cannot forge a case handover, because the repository validates the original case reporter, work state, paused session and conversation ownership under row locks.
- Only the already assigned case supervisor can record containment and remediation notes; a different manager, stale revision or changed work status is rejected.
- Each source-linked handover contains current state titles and status as an auditable snapshot, not a signed certification.
- No unapproved SOP modification or bypass of physical inspection, supervisor gates or evidence requirements is permitted.

## Acceptance
- Migration 011 safely runs twice, with tenant isolation inherited from both case and shift-handover tables.
- API tests validate employee scope and payload rejection of forged department, conversation or work state.
- PostgreSQL test validates original reporter only, one-to-one handover, no duplicate, preserved blocked state and session, containment-first remediation, stale revision denial and cross-department RLS.
- Chromium tests the actual Phase 3B SOP exception, a worker-filed handover, supervisor-linked case, containment, remediation proposal and persistence of blocked work; legacy handovers and Phase 1–4A acceptance still run.
- All frontend, security and browser gates must pass on the *exact* integration commit. Production remains NO_GO pending operational QA, independent safety approvals and site sign-off.

## Next: Phase 4C and Phase 5
- Phase 4C: independent supervisor sign-offs on a tested corrective SOP/re-entry policy (with no generic "unblock" button), explicit new execution session or fresh task when authorized, and handover/case resolution semantics.
- Phase 5: in-context multilingual AI on active tasks and real source-grounded SOP versions, verified Hindi/English/Hinglish speech workflows and voice acceptance.

## Integration
PR #33 is stacked on Phase 4A #32, which stacks on Phase 3B #31, 3A #30, Phase 2 #29, Phase 1 #28 and the earlier PostgreSQL migration chain. Keep as a draft pending exact-head green CI and appropriate human review. Do not merge directly to old main.
