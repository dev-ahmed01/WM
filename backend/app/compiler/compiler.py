"""OWD Relational Compiler Module (v1.1 Knowledge Compiler).

Responsible ONLY for converting a validated UnifiedAST into a CompiledWorkflow object
containing database-ready payload dictionaries for all 15 normalized Snowflake tables.
Does NOT execute SQL statements.
"""

import re
import logging
from typing import Dict, Any, List

from app.compiler.models import UnifiedAST, CompiledWorkflow
from app.compiler.utils import generate_deterministic_uuid
from app.compiler.exceptions import OWDCompilationException
from app.core.config import settings

logger = logging.getLogger("compiler.transformer")


class OWDCompiler:
    """Transforms validated UnifiedAST graphs into normalized relational entity payloads."""

    @staticmethod
    def compile(owd_document: UnifiedAST, stage_file_uri: str = "", user_id: str = "admin") -> CompiledWorkflow:
        """Transforms UnifiedAST into database-ready CompiledWorkflow object."""
        if not owd_document or not owd_document.workflow:
            raise OWDCompilationException("Cannot compile empty or uninitialized OWD Document.")

        wf = owd_document.workflow
        meta = owd_document.metadata
        ret_meta = owd_document.retrieval_metadata
        wf_def = owd_document.workflow_definition
        u_ctx = owd_document.user_context
        analytics = owd_document.analytics

        workflow_id = generate_deterministic_uuid("workflow", wf.workflow_code)
        version_id = generate_deterministic_uuid("version", f"{wf.workflow_code}_v{wf.version_number}")

        # 1. Root Workflow Payload (KNOWLEDGE_STUDIO.workflows)
        workflow_payload = {
            "id": workflow_id,
            "workflow_code": wf.workflow_code,
            "title": wf.title,
            "description": wf.description or (wf_def.workflow_objective if wf_def else f"Compiled OWD workflow for {wf.title}"),
            "department_id": wf.department_id,
            "category": wf.category,
            "created_by": user_id,
            "owner": meta.owner if meta else "System Admin",
            "priority": meta.priority if meta else "MEDIUM",
            "difficulty": meta.difficulty if meta else "INTERMEDIATE",
            "estimated_duration": meta.estimated_duration if meta else "30 mins",
            "review_cycle": meta.review_cycle if meta else "ANNUAL",
            "effective_date": meta.effective_date if meta else "2026-01-01",
            "workflow_objective": wf_def.workflow_objective if wf_def else f"Execute {wf.title}",
            "business_goal": wf_def.business_goal if wf_def else "Process Compliance",
            "entry_conditions": ", ".join(wf_def.entry_conditions) if (wf_def and wf_def.entry_conditions) else "Standard Entry",
            "exit_conditions": ", ".join(wf_def.exit_conditions) if (wf_def and wf_def.exit_conditions) else "Standard Exit",
        }

        # 2. Workflow Version Payload (KNOWLEDGE_STUDIO.workflow_versions)
        version_payload = {
            "id": version_id,
            "workflow_id": workflow_id,
            "version_number": wf.version_number,
            "semantic_version": meta.version if (meta and meta.version) else f"{wf.version_number}.0.0",
            "stage_file_uri": stage_file_uri or f"@{settings.SNOWFLAKE_STAGE_NAME}/{wf.workflow_code}_v{wf.version_number}.md",
            "ast_hash": owd_document.raw_source_hash,
            "status": "compiled",
        }

        # State Key -> UUID mapping
        state_key_to_id: Dict[str, str] = {}
        for s in wf.states:
            state_key_to_id[s.state_key] = generate_deterministic_uuid("state", f"{version_id}_{s.state_key}")

        states_payload: List[Dict[str, Any]] = []
        steps_payload: List[Dict[str, Any]] = []
        transitions_payload: List[Dict[str, Any]] = []
        decisions_payload: List[Dict[str, Any]] = []
        decision_options_payload: List[Dict[str, Any]] = []
        rules_payload: List[Dict[str, Any]] = []
        evidence_specs_payload: List[Dict[str, Any]] = []
        ai_conversation_payload: List[Dict[str, Any]] = []
        search_metadata_payload: List[Dict[str, Any]] = []

        # 3. Process States, Steps, Decisions, AI Conversations, Rules
        for s in wf.states:
            s_id = state_key_to_id[s.state_key]
            states_payload.append({
                "id": s_id,
                "workflow_version_id": version_id,
                "state_key": s.state_key,
                "state_type": s.state_type,
                "title": s.title,
                "description": s.description or s.title,
                "is_initial": s.is_initial,
                "is_terminal": s.is_terminal,
                "ordinal_index": s.ordinal_index,
                "purpose": s.purpose or s.title,
                "entry_condition": s.entry_condition or "None",
                "exit_condition": s.exit_condition or "State Completed",
                "responsible_role": s.responsible_role or "Employee",
                "expected_duration": s.expected_duration or "10 mins",
                "business_objective": s.business_objective or s.title,
            })

            # Steps & AI Conversations
            for st in s.steps:
                st_id = generate_deterministic_uuid("step", f"{s_id}_{st.step_code}")
                prompt_text = st.ai_guidance.prompt_template if st.ai_guidance else f"Assist employee with step: {st.instruction}"

                steps_payload.append({
                    "id": st_id,
                    "state_id": s_id,
                    "step_code": st.step_code,
                    "instruction": st.instruction,
                    "ai_guidance_prompt": prompt_text,
                    "expected_output_type": st.expected_output_type,
                    "is_mandatory": st.is_mandatory,
                    "ordinal_index": st.ordinal_index,
                    "sequence_number": st.sequence_number,
                    "safety_note": st.safety_note or "None",
                    "estimated_time": st.estimated_time,
                    "retry_policy": st.retry_policy,
                    "completion_criteria": st.completion_criteria,
                    "common_failure": st.common_failure or "Operator delay",
                    "recovery_action": st.recovery_action or "Retry step",
                })

                # AI Conversation Layer (Section 6)
                if st.ai_conversation:
                    conv = st.ai_conversation
                    conv_id = generate_deterministic_uuid("ai_conv", f"{st_id}_conv")
                    ai_conversation_payload.append({
                        "id": conv_id,
                        "step_id": st_id,
                        "question_ai_should_ask": conv.question_ai_should_ask,
                        "expected_user_responses": ", ".join(conv.expected_user_responses),
                        "clarification_questions": ", ".join(conv.clarification_questions),
                        "fallback_prompt": conv.fallback_prompt or "Please clarify response.",
                        "coaching_prompt": conv.coaching_prompt or "Follow standard operating guidelines.",
                        "escalation_trigger": conv.escalation_trigger or "MAX_RETRIES_EXCEEDED",
                        "confidence_requirements": conv.confidence_requirements,
                        "citation_source": conv.citation_source or "SOP_STANDARD",
                    })

                # Evidence Specs
                for e in s.evidence_specs:
                    e_id = generate_deterministic_uuid("evidence", f"{st_id}_{e.evidence_code}")
                    evidence_specs_payload.append({
                        "id": e_id,
                        "step_id": st_id,
                        "evidence_type": e.evidence_type,
                        "validation_regex": None,
                        "min_size_bytes": e.min_size_bytes,
                        "is_required": e.is_required,
                    })

            # Decision Nodes & Options (Section 7)
            for d in s.decisions:
                d_id = generate_deterministic_uuid("dec", f"{s_id}_{d.decision_code}")
                decisions_payload.append({
                    "id": d_id,
                    "state_id": s_id,
                    "decision_code": d.decision_code,
                    "question": d.question,
                    "alternative_path": d.alternative_path or "None",
                    "business_rule": d.business_rule or "None",
                    "escalation_workflow": d.escalation_workflow or "None",
                })

                for opt in d.options:
                    if opt.target_state_key in state_key_to_id:
                        opt_target_id = state_key_to_id[opt.target_state_key]
                        opt_id = generate_deterministic_uuid("dec_opt", f"{s_id}_{opt.option_code}")
                        decision_options_payload.append({
                            "id": opt_id,
                            "state_id": s_id,
                            "option_code": opt.option_code,
                            "option_label": opt.option_label,
                            "target_state_id": opt_target_id,
                        })

            # Rules
            for r in s.safety_rules:
                r_id = generate_deterministic_uuid("rule", f"{s_id}_{r.rule_code}")
                rules_payload.append({
                    "id": r_id,
                    "state_id": s_id,
                    "rule_type": "SAFETY_GUARDRAIL",
                    "rule_code": r.rule_code,
                    "condition_logic": r.condition_logic,
                    "enforcement_level": r.enforcement_level,
                    "error_message": r.error_message,
                })

            for br in s.business_rules:
                br_id = generate_deterministic_uuid("rule", f"{s_id}_{br.rule_code}")
                mapped_rule_type = br.rule_type if br.rule_type in (
                    'SAFETY_GUARDRAIL', 'INPUT_VALIDATION', 'PREREQUISITE', 'COMPLIANCE_CHECK'
                ) else 'COMPLIANCE_CHECK'

                rules_payload.append({
                    "id": br_id,
                    "state_id": s_id,
                    "rule_type": mapped_rule_type,
                    "rule_code": br.rule_code,
                    "condition_logic": br.condition_logic,
                    "enforcement_level": "WARNING_CONFIRM",
                    "error_message": br.error_message,
                })

            # Transitions
            for t in s.transitions:
                if t.to_state_key in state_key_to_id:
                    target_id = state_key_to_id[t.to_state_key]
                    t_id = generate_deterministic_uuid("trans", f"{s_id}_{target_id}_{t.priority}")
                    transitions_payload.append({
                        "id": t_id,
                        "from_state_id": s_id,
                        "to_state_id": target_id,
                        "condition_type": t.condition_type,
                        "condition_expression": t.condition_expression,
                        "priority": t.priority,
                    })

            # Search Metadata (Section 2 & 9)
            step_text = " ".join([f"{st.step_code} {st.instruction}" for st in s.steps])
            rule_text = " ".join([f"{r.rule_code} {r.condition_logic}" for r in s.safety_rules + s.business_rules])
            kw_list = ret_meta.keywords if ret_meta and ret_meta.keywords else []
            combined_raw = f"{wf.title} {wf.workflow_code} {s.title} {step_text} {rule_text} {' '.join(kw_list)}"
            keywords = sorted(list(set(re.findall(r'\b[A-Za-z0-9_-]{3,}\b', combined_raw.upper()))))
            keywords_str = ", ".join(keywords[:25])

            sm_id = generate_deterministic_uuid("search", f"{version_id}_{s_id}")
            search_metadata_payload.append({
                "id": sm_id,
                "workflow_version_id": version_id,
                "state_id": s_id,
                "department_id": wf.department_id,
                "search_content": (
                    f"Title: {wf.title} | Code: {wf.workflow_code} | Department: {wf.department_id} | "
                    f"Category: {wf.category} | Type: OWD_WORKFLOW | Language: en-US | "
                    f"State: {s.title} ({s.state_key}) | Instructions: {step_text} | Rules: {rule_text} | "
                    f"Keywords: {keywords_str}"
                ),
                "embedding_ref": "none",
                "status": "published",
            })

        # 4. Analytics Payload (Section 9)
        analytics_payload: List[Dict[str, Any]] = []
        if analytics and analytics.events:
            for ev in analytics.events:
                ev_id = generate_deterministic_uuid("analytic", f"{version_id}_{ev.event_name}")
                analytics_payload.append({
                    "id": ev_id,
                    "workflow_version_id": version_id,
                    "event_name": ev.event_name,
                    "event_trigger": ev.event_trigger,
                    "kpis": ", ".join(ev.kpis),
                })

        # 5. Relationships Payload (Section 10)
        relationships_payload: List[Dict[str, Any]] = []
        if owd_document.relationships:
            for rel in owd_document.relationships:
                rel_id = generate_deterministic_uuid("rel", f"{version_id}_{rel.relationship_type}_{rel.target_reference}")
                relationships_payload.append({
                    "id": rel_id,
                    "workflow_version_id": version_id,
                    "relationship_type": rel.relationship_type,
                    "target_reference": rel.target_reference,
                    "description": rel.description or f"Edge to {rel.target_reference}",
                })

        # 6. References Payload (Section 11)
        references_payload: List[Dict[str, Any]] = []
        if owd_document.v1_1_references:
            for ref in owd_document.v1_1_references:
                ref_id = generate_deterministic_uuid("ref", f"{version_id}_{ref.reference_type}_{ref.title}")
                references_payload.append({
                    "id": ref_id,
                    "workflow_version_id": version_id,
                    "reference_type": ref.reference_type,
                    "title": ref.title,
                    "citation_uri": ref.citation_uri,
                })

        # 7. Role Permissions Payload (Section 8)
        role_permissions_payload: List[Dict[str, Any]] = []
        if u_ctx:
            for role in u_ctx.roles:
                perm_id = generate_deterministic_uuid("perm", f"{version_id}_{role}")
                role_permissions_payload.append({
                    "id": perm_id,
                    "workflow_version_id": version_id,
                    "role_name": role,
                    "required_permissions": ", ".join(u_ctx.permissions),
                    "experience_level": ", ".join(u_ctx.experience_levels),
                    "required_certifications": ", ".join(u_ctx.certifications),
                    "language_code": ", ".join(u_ctx.supported_languages),
                    "department_id": u_ctx.department or wf.department_id,
                })

        # 8. Enterprise Document Layer Payloads
        doc_id = generate_deterministic_uuid("doc", f"{version_id}_document")
        import hashlib
        raw_text = owd_document.raw_markdown or ""
        md5_val = hashlib.md5(raw_text.encode("utf-8")).hexdigest() if raw_text else None
        word_cnt = len(raw_text.split())

        # Ingestion is deterministic: derived metadata must never depend on an AI/network call.
        prose_lines = [
            line.strip().lstrip("# ") for line in raw_text.splitlines()
            if line.strip() and not line.lstrip().startswith(("::", "---", "#"))
        ]
        summary_txt = " ".join(prose_lines[:3])[:1000] or wf.description or wf.title
        entities_dict = {
            "workflow_code": wf.workflow_code,
            "department_id": wf.department_id,
            "state_keys": [state.state_key for state in wf.states],
        }

        documents_payload: List[Dict[str, Any]] = [{
            "id": doc_id,
            "workflow_id": workflow_id,
            "workflow_version_id": version_id,
            "document_name": wf.title,
            "original_filename": f"{wf.workflow_code}.md",
            "stage_uri": version_payload["stage_file_uri"],
            "relative_path": f"inbound/{wf.workflow_code}.md",
            "directory": "inbound",
            "extension": "md",
            "mime_type": "text/markdown",
            "file_size_bytes": len(raw_text),
            "compression": "none",
            "encoding": "utf-8",
            "md5_hash": md5_val,
            "sha256_hash": owd_document.raw_source_hash,
            "compiler_version": "1.1.0",
            "parser_version": "1.1.0",
            "source_type": "OWD_MARKDOWN",
            "language_code": "en-US",
            "author": owd_document.frontmatter.get("author") or (meta.owner if meta else "System Admin"),
            "reviewer": owd_document.frontmatter.get("reviewer") or "Supervisor",
            "approval_status": "APPROVED",
            "tags": [wf.category, wf.department_id],
            "labels": owd_document.frontmatter or {},
            "description": wf.description,
        }]

        contents_payload: List[Dict[str, Any]] = [{
            "id": generate_deterministic_uuid("content", f"{version_id}_content"),
            "document_id": doc_id,
            "workflow_version_id": version_id,
            "raw_markdown": raw_text,
            "normalized_markdown": raw_text,
            "frontmatter_yaml": owd_document.frontmatter_yaml,
            "frontmatter_json": owd_document.frontmatter,
            "body_markdown": raw_text,
            "sections_json": owd_document.sections,
            "tables_json": owd_document.tables,
            "code_blocks_json": owd_document.code_blocks,
            "images_json": owd_document.images,
            "links_json": owd_document.links,
        }]

        avg_chunk_sz = sum(len(sm["search_content"]) for sm in search_metadata_payload) // max(1, len(search_metadata_payload))
        ai_metadata_payload: List[Dict[str, Any]] = [{
            "id": generate_deterministic_uuid("ai_meta", f"{version_id}_ai_meta"),
            "document_id": doc_id,
            "workflow_version_id": version_id,
            "reading_time_minutes": max(1, word_cnt // 200),
            "word_count": word_cnt,
            "sentence_count": len(re.split(r"[.!?]+", raw_text)),
            "paragraph_count": len([p for p in raw_text.split("\n\n") if p.strip()]),
            "complexity_score": min(1.0, (len(steps_payload) + len(decisions_payload) * 2) / 100),
            "risk_score": min(1.0, len(rules_payload) / 50),
            "summary": summary_txt,
            "keywords": ret_meta.keywords if ret_meta else [],
            "entities": entities_dict,
            "language_detected": "en-US",
            "embedding_model": "none",
            "embedding_version": "not_applicable",
            "chunk_count": len(search_metadata_payload),
            "average_chunk_size": avg_chunk_sz,
            "embedding_status": "NOT_REQUIRED",
            "evaluation_score": None,
            "confidence_score": None,
        }]

        chunks_payload: List[Dict[str, Any]] = []
        for idx, sm in enumerate(search_metadata_payload, start=1):
            chunk_content = sm["search_content"]
            c_hash = hashlib.sha256(chunk_content.encode("utf-8")).hexdigest()
            chunks_payload.append({
                "id": generate_deterministic_uuid("chunk", f"{version_id}_{sm['state_id']}"),
                "document_id": doc_id,
                "workflow_version_id": version_id,
                "state_id": sm["state_id"],
                "step_id": None,
                "chunk_order": idx,
                "character_count": len(chunk_content),
                "token_count": len(chunk_content.split()),
                "chunk_content": chunk_content,
                "embedding_ref": "none",
                "vector_status": "NOT_REQUIRED",
                "chunk_hash": c_hash,
                "chunk_type": "STATE_STEP",
                "section_name": sm.get("state_id"),
            })

        lineage_payload: List[Dict[str, Any]] = [{
            "id": generate_deterministic_uuid("lineage", f"{version_id}_lineage"),
            "document_id": doc_id,
            "workflow_version_id": version_id,
            "stage_file_uri": version_payload["stage_file_uri"],
            "source_markdown_hash": owd_document.raw_source_hash,
            "parser_name": "OWDParser",
            "ast_hash": owd_document.raw_source_hash,
            "compiler_name": "OWDCompiler",
            "loader_name": "OWDLoader",
            "status": "PUBLISHED",
            "executed_by": "SYSTEM",
            "execution_notes": f"Successfully compiled {len(states_payload)} states into enterprise document object.",
        }]

        logger.info(
            f"[COMPILER SUCCESS] Compiled OWD v1.1 '{wf.workflow_code}' v{wf.version_number}: "
            f"{len(states_payload)} states, {len(steps_payload)} steps, {len(decisions_payload)} decisions, "
            f"{len(ai_conversation_payload)} AI conv blocks, {len(relationships_payload)} graph edges, "
            f"1 enterprise document object with {len(chunks_payload)} chunks."
        )

        return CompiledWorkflow(
            workflow_payload=workflow_payload,
            version_payload=version_payload,
            states_payload=states_payload,
            steps_payload=steps_payload,
            transitions_payload=transitions_payload,
            decisions_payload=decisions_payload,
            decision_options_payload=decision_options_payload,
            rules_payload=rules_payload,
            evidence_specs_payload=evidence_specs_payload,
            ai_conversation_payload=ai_conversation_payload,
            analytics_payload=analytics_payload,
            relationships_payload=relationships_payload,
            references_payload=references_payload,
            role_permissions_payload=role_permissions_payload,
            search_metadata_payload=search_metadata_payload,
            documents_payload=documents_payload,
            contents_payload=contents_payload,
            ai_metadata_payload=ai_metadata_payload,
            chunks_payload=chunks_payload,
            lineage_payload=lineage_payload,
        )
