# WorkMate Phase 5A — contextual guidance within active work

## Product
The frontline employee no longer needs to navigate to a disconnected generic chatbot. A compact **Ask about this task** panel lives alongside the actual checkpoint, evidence form and action controls on an assigned task.

The panel has four read-only actions: explain the current published step, explain its evidence requirements, provide a safety/exception escalation reminder, or search approved departmental reference materials for a typed question.

## Authority and safety
- Task authorization is enforced through the **existing** scoped `WorkExecutionRepository.position`, checking the authenticated department, assignee or authorized manager. No task state or evidence is changed by guidance.
- The current workflow version, state ID, step ID and structured evidence specifications come from the persisted published SOP execution graph. No model-generated instructions become executable.
- The approved-reference question path reuses the current hybrid retrieval and exact-quote provenance checks. It is supplemental reference information, **not authority to supersede the published work procedure**.
- When no approved reference supports a question or the retrieval service fails, the endpoint fails closed, gives the existing published step as the only cited operational guidance, and recommends supervisor clarification.
- A blocked task always returns its actual case reference and a stop instruction, even if the free-form prompt asks for a bypass. A manager's own access cannot turn the endpoint into a workflow override.
- Questions are bounded to 500 characters and outputs are rendered as text; the frontend resets guidance when the real state/step or task status changes, so a stale response is not presented as the new step.
- The source metadata and citations are specific to the authenticated task/approved reference and may not be fabricated by the browser.

## Acceptance
- Backend API role/department scope and rejection of client department overrides.
- Unit tests of one published checkpoint, mandatory JPEG evidence, blocked-work fail-closed response, approved exact-reference citation, missing-reference fallback and invalid questions.
- Chromium acceptance on actual post-Publishing task: describe current checkpoint, check required evidence before and after progression, verify current workflow version in citation, and deny cross-department user access.
- Full backend regression, frontend typecheck/build, real PostgreSQL acceptance and staging role security.

## Limits and next phase
This phase adds **contextual, read-only, source-grounded help** through the already-existing local/hybrid retrieval service. It does not establish a new autonomous AI planner, high-stakes safety verification, voice model accuracy or multilingual speech reliability. Some questions will receive a conservative fallback rather than a fluent unsupported answer. Phase 5B will add Hindi/English/Hinglish speech input and transcript confirmation inside task context, with explicit field-audio quality tests and no voice-triggered bypass of mandatory evidence. Production pilot remains NO_GO until site-specific release evidence is accepted.

## Integration order
PR #35 is stacked onto fully verified Phase 4C #34, then Phase 4B #33, 4A #32, 3B #31, 3A #30, Phase 2 #29, Phase 1 #28 and the existing PostgreSQL foundation. It remains draft and not merged to old main.
