# WorkMate Phase 3B — Visual procedure publishing

## Architecture
This release closes the loop **ordinary document → extracted suggestions → administrator-reviewed steps → compiler-validated OWD → explicit publish → real work assignment**.

- Phase 3A original sources, step provenance, revision checking, and administrator review remain unchanged.
- Visual authors edit typed outputs (confirmation, observation, numerical reading, file) and required JPEG/PDF attachments per step; optional final-outcome decisions can split into terminal completion or supervisor hold.
- `procedure_plan.render_owd` produces auditable Markdown as an **adapter** to the existing OWDParser/Validator/Compiler/Loader. No second workflow engine is allowed.
- `procedure_publisher.publish` locks one reviewed draft revision; inserts the generated source object; runs canonical OWD compile/load in the **same PostgreSQL transaction**; and links a published version to the source draft. Any failed statement rolls back every write. Replays and stale revision submissions fail.
- Worker tasks bind only a published version from their own department. The existing Phase 2 state machine checks current step, mandatory evidence and safety gates.

## Safety boundaries
1. Only administrators of the owning department can preview/publish, with an explicit confirmation literal.
2. A draft must be reviewed and unchanged. Extraction alone cannot publish.
3. Numeric, confirmation and text steps are **worker attestations**. JPEG/PDF files are validated and stored privately as received-but-unverified, not certified proof of physical conditions.
4. A final outcome requiring supervisor review generates a non-terminal `ESCALATION` state with a `HARD_STOP` rule. Worker self-completion and bypass are disabled. Follow-on Phase 4 implements the supervisor resolution and task-linked case workflow.
5. OWD compilation must pass canonical graph validation before database persistence. Unsupported evidence/rule types fail closed in execution.
6. New versions are immutable operational inputs; published phase status does not override independent safety/site approvals.
7. Original SOP files remain available from the source-backed draft with administrator and department scoping.
8. No WMS/ERP device integration or independent site certification is claimed.

## Acceptance
- Migration 009 can be re-applied safely and enforces exactly one published version for each published draft.
- `test_procedure_publishing_api.py` tests valid source-derived steps, branch and safety-hold compilation, invalid proof definitions, administrator authorization and literal confirmation.
- CI: clean PostgreSQL schema + existing workflow regression tests + Next.js typecheck/build + staging RLS.
- Browser acceptance: upload normal SOP; verify source; set text observation, photo and decision paths; save, re-review; compile preview; explicitly publish; reject duplicate publish; create assignment as manager; bind generated version; worker confirms step 1, records text and JPEG at step 2, selects safe decision and completes. Wrong-department access remains denied.
- The *exception path* remains held for supervisor action and is never reported as automatically resolved.

## Branch integration
PR #31 is stacked on Procedure Studio Phase 3A #30, guided execution Phase 2 #29, Phase 1 #28 and earlier PostgreSQL migrations. Keep the draft PR until exact-HEAD CI passes. Do not merge into stale main or represent the Vercel preview as a hosted backend production environment.

## Next release
Phase 4 unifies task-linked exceptions and handovers, supervisor ownership and human approval, replayable state/event timeline, aging, and operational insights from real execution records.
