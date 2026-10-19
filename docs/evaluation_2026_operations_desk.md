# WorkMate evaluation edition — Operations Desk

## Research-backed design direction

The goal is not to imitate generic chat. WorkMate links department-authorized evidence, versioned procedures, step state, and worker confirmation. Glean and Guru demonstrate the importance of cited and permission-aware evidence; Microsoft Copilot exposes grounded knowledge-source agents; frontline manufacturing guidance emphasizes task context and bounded operator actions.

References (reviewed 2026-10-20):
- Glean citations: https://docs.glean.com/user-guide/assistant/glean-chat/glean-chat-citations/glean-citations
- Guru knowledge agents: https://www.getguru.com/features/knowledge-agents
- Microsoft Agent Builder sources: https://learn.microsoft.com/en-us/microsoft-365/copilot/extensibility/agent-builder-add-knowledge
- Google Cloud manufacturing workflows: https://cloud.google.com/gemini-enterprise/resources/prompt-guide

## Implemented phase — operator experience

- New authenticated Operations Desk at /workspace for all roles, with real user department/role and real history counts, resumable conversations, starter tasks, and an editable prompt builder.
- Four examples: inbound receiving, discrepancy, damaged putaway, and policy lookup. Examples are *not* asserted to be published procedures. They prefill Copilot for human review; no automatic workflow or AI request is fired.
- Role-aware navigation includes Operations Desk. Employee login lands on the desk; admin and manager keep their existing primary surfaces.
- Copilot accepts 500-character bounded draft and validated mode query params, and does not confuse an existing session with a new draft.
- Answers can be locally copied or exported with source excerpts, document titles, version/section/step metadata when available, and explicit unverified/possible-escalation status. An export is NOT a signed audit record or a substitute for original documentation.

## Demo sequence (requires approved sample content)

1. Sign in as employee; show department-specific desk and task cards.
2. Choose Receiving; review the prefilled Copilot prompt; send. The backend must identify a genuinely published receiving SOP or abstain.
3. Advance one authorized step and show pause/resume where allowed.
4. Choose Find a policy; switch to reference mode and ask a question backed by an *approved* reference. Expand citations; export evidence note.
5. Demonstrate refusal with a department-unauthorized or unapproved document.
6. Record a Hindi/Hinglish phrase, correct any transcript errors, and explicitly send (subject to provisioned voice runtime).
7. Open Session history and resume. For admin, review versioned sources; for manager, open Intelligence Hub and pilot summary.

## Acceptance checklist and honest limits

- [ ] Pull request frontend typecheck/build green.
- [ ] Existing full backend and PostgreSQL quality suite green.
- [ ] Chromium end-to-end smoke passes on changed branch.
- [ ] Human checks keyboard/mobile navigation, desktop session resume, source export, microphone permissions.
- [ ] Rehearse with approved non-sensitive sample SOP/reference documents.
- [ ] Separately verify live Ollama and actual English/Hindi/Hinglish microphone accuracy; synthetic CI cannot establish these.
- [ ] Do not describe evidence export as legally signed, source approval as external fact-checking, or sample data as production.
- [ ] Hosted TLS, external disaster recovery, and actual field acceptance remain release gates.

## Follow-on evaluation roadmap

**Phase B — evidence-aware collaboration:** source comparison and manager-approved handover records, with auditable DB persistence.
**Phase C — advanced task reasoning:** state-specific exception decision capture, escalation ownership, and independently evaluated Hindi/Hinglish benchmarks.
**Phase D — release acceptance:** real browsers against hosted TLS, validated recovery and security configuration, field cohort accuracy, latency, and human sign-off.

Do not add fictitious analytics or pretend these follow-on phases are already implemented.
