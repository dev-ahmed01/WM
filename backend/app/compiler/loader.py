"""OWD Snowflake Database Loader Module (v1.1 Knowledge Compiler).

Responsible ONLY for persisting compiled OWD relational payload structures into Snowflake
tables across all 15 normalized tables using MERGE/INSERT SQL commands.
Does NOT perform markdown parsing or validation.
"""

import logging
from typing import List, Dict, Any, Optional

from app.compiler.models import CompiledWorkflow, LoadResult
from app.compiler.exceptions import OWDLoaderException

try:
    from app.core.database import get_snowflake_connection  # type: ignore
except ImportError:
    get_snowflake_connection = None

logger = logging.getLogger("compiler.loader")


class OWDLoader:
    """Persists compiled OWD relational entity payloads into Snowflake database tables."""

    @staticmethod
    def get_workflow_version_by_hash(workflow_code: str, ast_hash: str) -> Optional[Dict[str, Any]]:
        """Queries Snowflake to check if a workflow version matching ast_hash already exists."""
        if get_snowflake_connection is None:
            return None
        try:
            with get_snowflake_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT v.id, v.workflow_id, v.version_number, v.ast_hash
                        FROM KNOWLEDGE_STUDIO.workflow_versions v
                        JOIN KNOWLEDGE_STUDIO.workflows w ON v.workflow_id = w.id
                        WHERE w.workflow_code = %s AND v.ast_hash = %s
                        LIMIT 1
                        """,
                        (workflow_code, ast_hash),
                    )
                    row = cur.fetchone()
                    if row:
                        return {"id": row[0], "workflow_id": row[1], "version_number": row[2], "ast_hash": row[3]}
        except Exception as exc:
            logger.warning(f"[LOADER HASH CHECK SKIPPED] Query failed: {exc}")
        return None

    @staticmethod
    def get_latest_version_number(workflow_code: str) -> int:
        """Queries Snowflake for the highest version_number recorded for a workflow_code."""
        if get_snowflake_connection is None:
            return 0
        try:
            with get_snowflake_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT COALESCE(MAX(v.version_number), 0)
                        FROM KNOWLEDGE_STUDIO.workflow_versions v
                        JOIN KNOWLEDGE_STUDIO.workflows w ON v.workflow_id = w.id
                        WHERE w.workflow_code = %s
                        """,
                        (workflow_code,),
                    )
                    row = cur.fetchone()
                    if row and row[0] is not None:
                        return int(row[0])
        except Exception as exc:
            logger.warning(f"[LOADER VERSION CHECK SKIPPED] Query failed: {exc}")
        return 0

    @staticmethod
    def load(compiled_workflow: CompiledWorkflow) -> LoadResult:
        """Executes transactional MERGE/INSERT statements against Snowflake KNOWLEDGE_STUDIO tables."""
        if not compiled_workflow or not compiled_workflow.workflow_payload:
            raise OWDLoaderException("Cannot load null or uninitialized CompiledWorkflow payload.")

        if get_snowflake_connection is None:
            raise OWDLoaderException("Database connection module unavailable: get_snowflake_connection is not loaded.")

        wf = compiled_workflow.workflow_payload
        ver = compiled_workflow.version_payload
        states = compiled_workflow.states_payload
        steps = compiled_workflow.steps_payload
        transitions = compiled_workflow.transitions_payload
        decisions = compiled_workflow.decisions_payload
        decision_options = compiled_workflow.decision_options_payload
        rules = compiled_workflow.rules_payload
        evidence_specs = compiled_workflow.evidence_specs_payload
        ai_conversation = compiled_workflow.ai_conversation_payload
        analytics = compiled_workflow.analytics_payload
        relationships = compiled_workflow.relationships_payload
        references = compiled_workflow.references_payload
        role_permissions = compiled_workflow.role_permissions_payload
        search_metadata = compiled_workflow.search_metadata_payload

        documents = getattr(compiled_workflow, "documents_payload", [])
        contents = getattr(compiled_workflow, "contents_payload", [])
        ai_metadata = getattr(compiled_workflow, "ai_metadata_payload", [])
        chunks = getattr(compiled_workflow, "chunks_payload", [])
        lineage = getattr(compiled_workflow, "lineage_payload", [])

        tables_updated: List[str] = []

        conn = None
        try:
            with get_snowflake_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("BEGIN")
                    # 1. Upsert Root Workflow
                    cur.execute(
                        """
                        MERGE INTO KNOWLEDGE_STUDIO.workflows AS target
                        USING (SELECT %s AS id, %s AS workflow_code, %s AS title, %s AS description, %s AS department_id, %s AS category, %s AS created_by,
                                      %s AS owner, %s AS priority, %s AS difficulty, %s AS estimated_duration, %s AS review_cycle, %s AS effective_date,
                                      %s AS workflow_objective, %s AS business_goal, %s AS entry_conditions, %s AS exit_conditions) AS src
                        ON target.id = src.id OR target.workflow_code = src.workflow_code
                        WHEN MATCHED THEN UPDATE SET title = src.title, description = src.description, department_id = src.department_id, updated_at = CURRENT_TIMESTAMP(),
                                                     owner = src.owner, priority = src.priority, difficulty = src.difficulty, estimated_duration = src.estimated_duration,
                                                     workflow_objective = src.workflow_objective, business_goal = src.business_goal
                        WHEN NOT MATCHED THEN INSERT (id, workflow_code, title, description, department_id, category, created_by, created_at, updated_at,
                                                     owner, priority, difficulty, estimated_duration, review_cycle, effective_date, workflow_objective, business_goal, entry_conditions, exit_conditions)
                        VALUES (src.id, src.workflow_code, src.title, src.description, src.department_id, src.category, src.created_by, CURRENT_TIMESTAMP(), CURRENT_TIMESTAMP(),
                                src.owner, src.priority, src.difficulty, src.estimated_duration, src.review_cycle, src.effective_date, src.workflow_objective, src.business_goal, src.entry_conditions, src.exit_conditions)
                        """,
                        (wf["id"], wf["workflow_code"], wf["title"], wf["description"], wf["department_id"], wf["category"], wf["created_by"],
                         wf.get("owner"), wf.get("priority"), wf.get("difficulty"), wf.get("estimated_duration"), wf.get("review_cycle"), wf.get("effective_date"),
                         wf.get("workflow_objective"), wf.get("business_goal"), wf.get("entry_conditions"), wf.get("exit_conditions")),
                    )
                    tables_updated.append("KNOWLEDGE_STUDIO.workflows")

                    # 2. Upsert Workflow Version
                    cur.execute(
                        """
                        MERGE INTO KNOWLEDGE_STUDIO.workflow_versions AS target
                        USING (SELECT %s AS id, %s AS workflow_id, %s AS version_number, %s AS semantic_version, %s AS stage_file_uri, %s AS ast_hash, %s AS status) AS src
                        ON target.id = src.id
                        WHEN MATCHED THEN UPDATE SET status = 'published', stage_file_uri = src.stage_file_uri, ast_hash = src.ast_hash, published_at = CURRENT_TIMESTAMP()
                        WHEN NOT MATCHED THEN INSERT (id, workflow_id, version_number, semantic_version, stage_file_uri, ast_hash, status, created_at, published_at)
                        VALUES (src.id, src.workflow_id, src.version_number, src.semantic_version, src.stage_file_uri, src.ast_hash, 'published', CURRENT_TIMESTAMP(), CURRENT_TIMESTAMP())
                        """,
                        (ver["id"], ver["workflow_id"], ver["version_number"], ver["semantic_version"], ver["stage_file_uri"], ver["ast_hash"], ver["status"]),
                    )
                    tables_updated.append("KNOWLEDGE_STUDIO.workflow_versions")

                    # 3. Insert Workflow States
                    for s in states:
                        cur.execute(
                            """
                            MERGE INTO KNOWLEDGE_STUDIO.workflow_states AS target
                            USING (SELECT %s AS id, %s AS workflow_version_id, %s AS state_key, %s AS state_type, %s AS title, %s AS description, %s AS is_initial, %s AS is_terminal, %s AS ordinal_index,
                                          %s AS purpose, %s AS entry_condition, %s AS exit_condition, %s AS responsible_role, %s AS expected_duration, %s AS business_objective) AS src
                            ON target.id = src.id
                            WHEN MATCHED THEN UPDATE SET title = src.title, description = src.description, purpose = src.purpose
                            WHEN NOT MATCHED THEN INSERT (id, workflow_version_id, state_key, state_type, title, description, is_initial, is_terminal, ordinal_index, purpose, entry_condition, exit_condition, responsible_role, expected_duration, business_objective)
                            VALUES (src.id, src.workflow_version_id, src.state_key, src.state_type, src.title, src.description, src.is_initial, src.is_terminal, src.ordinal_index, src.purpose, src.entry_condition, src.exit_condition, src.responsible_role, src.expected_duration, src.business_objective)
                            """,
                            (s["id"], s["workflow_version_id"], s["state_key"], s["state_type"], s["title"], s["description"], s["is_initial"], s["is_terminal"], s["ordinal_index"],
                             s.get("purpose"), s.get("entry_condition"), s.get("exit_condition"), s.get("responsible_role"), s.get("expected_duration"), s.get("business_objective")),
                        )
                    tables_updated.append("KNOWLEDGE_STUDIO.workflow_states")

                    # 4. Insert Steps
                    for st in steps:
                        cur.execute(
                            """
                            MERGE INTO KNOWLEDGE_STUDIO.workflow_steps AS target
                            USING (SELECT %s AS id, %s AS state_id, %s AS step_code, %s AS instruction, %s AS ai_guidance_prompt, %s AS expected_output_type, %s AS is_mandatory, %s AS ordinal_index,
                                          %s AS sequence_number, %s AS safety_note, %s AS estimated_time, %s AS retry_policy, %s AS completion_criteria, %s AS common_failure, %s AS recovery_action) AS src
                            ON target.id = src.id
                            WHEN MATCHED THEN UPDATE SET instruction = src.instruction
                            WHEN NOT MATCHED THEN INSERT (id, state_id, step_code, instruction, ai_guidance_prompt, expected_output_type, is_mandatory, ordinal_index, sequence_number, safety_note, estimated_time, retry_policy, completion_criteria, common_failure, recovery_action)
                            VALUES (src.id, src.state_id, src.step_code, src.instruction, src.ai_guidance_prompt, src.expected_output_type, src.is_mandatory, src.ordinal_index, src.sequence_number, src.safety_note, src.estimated_time, src.retry_policy, src.completion_criteria, src.common_failure, src.recovery_action)
                            """,
                            (st["id"], st["state_id"], st["step_code"], st["instruction"], st["ai_guidance_prompt"], st["expected_output_type"], st["is_mandatory"], st["ordinal_index"],
                             st.get("sequence_number"), st.get("safety_note"), st.get("estimated_time"), st.get("retry_policy"), st.get("completion_criteria"), st.get("common_failure"), st.get("recovery_action")),
                        )
                    if steps:
                        tables_updated.append("KNOWLEDGE_STUDIO.workflow_steps")

                    # 5. Insert Transitions
                    for t in transitions:
                        cur.execute(
                            """
                            MERGE INTO KNOWLEDGE_STUDIO.workflow_transitions AS target
                            USING (SELECT %s AS id, %s AS from_state_id, %s AS to_state_id, %s AS condition_type, %s AS condition_expression, %s AS priority) AS src
                            ON target.id = src.id
                            WHEN MATCHED THEN UPDATE SET priority = src.priority
                            WHEN NOT MATCHED THEN INSERT (id, from_state_id, to_state_id, condition_type, condition_expression, priority)
                            VALUES (src.id, src.from_state_id, src.to_state_id, src.condition_type, src.condition_expression, src.priority)
                            """,
                            (t["id"], t["from_state_id"], t["to_state_id"], t["condition_type"], t["condition_expression"], t["priority"]),
                        )
                    if transitions:
                        tables_updated.append("KNOWLEDGE_STUDIO.workflow_transitions")

                    # 6. Insert Decisions
                    for d in decisions:
                        cur.execute(
                            """
                            MERGE INTO KNOWLEDGE_STUDIO.workflow_decisions AS target
                            USING (SELECT %s AS id, %s AS state_id, %s AS decision_code, %s AS question, %s AS alternative_path, %s AS business_rule, %s AS escalation_workflow) AS src
                            ON target.id = src.id
                            WHEN MATCHED THEN UPDATE SET question = src.question
                            WHEN NOT MATCHED THEN INSERT (id, state_id, decision_code, question, alternative_path, business_rule, escalation_workflow)
                            VALUES (src.id, src.state_id, src.decision_code, src.question, src.alternative_path, src.business_rule, src.escalation_workflow)
                            """,
                            (d["id"], d["state_id"], d["decision_code"], d["question"], d.get("alternative_path"), d.get("business_rule"), d.get("escalation_workflow")),
                        )
                    if decisions:
                        tables_updated.append("KNOWLEDGE_STUDIO.workflow_decisions")

                    # 7. Insert Decision Options
                    for opt in decision_options:
                        cur.execute(
                            """
                            MERGE INTO KNOWLEDGE_STUDIO.workflow_decision_options AS target
                            USING (SELECT %s AS id, %s AS state_id, %s AS option_code, %s AS option_label, %s AS target_state_id) AS src
                            ON target.id = src.id
                            WHEN MATCHED THEN UPDATE SET option_label = src.option_label
                            WHEN NOT MATCHED THEN INSERT (id, state_id, option_code, option_label, target_state_id)
                            VALUES (src.id, src.state_id, src.option_code, src.option_label, src.target_state_id)
                            """,
                            (opt["id"], opt["state_id"], opt["option_code"], opt["option_label"], opt["target_state_id"]),
                        )
                    if decision_options:
                        tables_updated.append("KNOWLEDGE_STUDIO.workflow_decision_options")

                    # 8. Insert Rules
                    for r in rules:
                        cur.execute(
                            """
                            MERGE INTO KNOWLEDGE_STUDIO.workflow_rules AS target
                            USING (SELECT %s AS id, %s AS state_id, %s AS rule_type, %s AS rule_code, %s AS condition_logic, %s AS enforcement_level, %s AS error_message) AS src
                            ON target.id = src.id
                            WHEN MATCHED THEN UPDATE SET condition_logic = src.condition_logic
                            WHEN NOT MATCHED THEN INSERT (id, state_id, rule_type, rule_code, condition_logic, enforcement_level, error_message)
                            VALUES (src.id, src.state_id, src.rule_type, src.rule_code, src.condition_logic, src.enforcement_level, src.error_message)
                            """,
                            (r["id"], r["state_id"], r["rule_type"], r["rule_code"], r["condition_logic"], r["enforcement_level"], r["error_message"]),
                        )
                    if rules:
                        tables_updated.append("KNOWLEDGE_STUDIO.workflow_rules")

                    # 9. Insert Evidence Specs
                    for e in evidence_specs:
                        cur.execute(
                            """
                            MERGE INTO KNOWLEDGE_STUDIO.workflow_evidence_specs AS target
                            USING (SELECT %s AS id, %s AS step_id, %s AS evidence_type, %s AS validation_regex, %s AS min_size_bytes, %s AS is_required) AS src
                            ON target.id = src.id
                            WHEN MATCHED THEN UPDATE SET is_required = src.is_required
                            WHEN NOT MATCHED THEN INSERT (id, step_id, evidence_type, validation_regex, min_size_bytes, is_required)
                            VALUES (src.id, src.step_id, src.evidence_type, src.validation_regex, src.min_size_bytes, src.is_required)
                            """,
                            (e["id"], e["step_id"], e["evidence_type"], e.get("validation_regex"), e.get("min_size_bytes"), e["is_required"]),
                        )
                    if evidence_specs:
                        tables_updated.append("KNOWLEDGE_STUDIO.workflow_evidence_specs")

                    # 10. Insert AI Conversation Layer
                    for conv in ai_conversation:
                        cur.execute(
                            """
                            MERGE INTO KNOWLEDGE_STUDIO.workflow_ai_conversation AS target
                            USING (SELECT %s AS id, %s AS step_id, %s AS question_ai_should_ask, %s AS expected_user_responses, %s AS clarification_questions, %s AS fallback_prompt, %s AS coaching_prompt, %s AS escalation_trigger, %s AS confidence_requirements, %s AS citation_source) AS src
                            ON target.id = src.id
                            WHEN MATCHED THEN UPDATE SET question_ai_should_ask = src.question_ai_should_ask
                            WHEN NOT MATCHED THEN INSERT (id, step_id, question_ai_should_ask, expected_user_responses, clarification_questions, fallback_prompt, coaching_prompt, escalation_trigger, confidence_requirements, citation_source)
                            VALUES (src.id, src.step_id, src.question_ai_should_ask, src.expected_user_responses, src.clarification_questions, src.fallback_prompt, src.coaching_prompt, src.escalation_trigger, src.confidence_requirements, src.citation_source)
                            """,
                            (conv["id"], conv["step_id"], conv["question_ai_should_ask"], conv.get("expected_user_responses"), conv.get("clarification_questions"), conv.get("fallback_prompt"), conv.get("coaching_prompt"), conv.get("escalation_trigger"), conv.get("confidence_requirements"), conv.get("citation_source")),
                        )
                    if ai_conversation:
                        tables_updated.append("KNOWLEDGE_STUDIO.workflow_ai_conversation")

                    # 11. Insert Analytics Events
                    for an in analytics:
                        cur.execute(
                            """
                            MERGE INTO KNOWLEDGE_STUDIO.workflow_analytics AS target
                            USING (SELECT %s AS id, %s AS workflow_version_id, %s AS event_name, %s AS event_trigger, %s AS kpis) AS src
                            ON target.id = src.id
                            WHEN MATCHED THEN UPDATE SET event_trigger = src.event_trigger
                            WHEN NOT MATCHED THEN INSERT (id, workflow_version_id, event_name, event_trigger, kpis)
                            VALUES (src.id, src.workflow_version_id, src.event_name, src.event_trigger, src.kpis)
                            """,
                            (an["id"], an["workflow_version_id"], an["event_name"], an["event_trigger"], an.get("kpis")),
                        )
                    if analytics:
                        tables_updated.append("KNOWLEDGE_STUDIO.workflow_analytics")

                    # 12. Insert Knowledge Relationships
                    for rel in relationships:
                        cur.execute(
                            """
                            MERGE INTO KNOWLEDGE_STUDIO.workflow_relationships AS target
                            USING (SELECT %s AS id, %s AS workflow_version_id, %s AS relationship_type, %s AS target_reference, %s AS description) AS src
                            ON target.id = src.id
                            WHEN MATCHED THEN UPDATE SET target_reference = src.target_reference
                            WHEN NOT MATCHED THEN INSERT (id, workflow_version_id, relationship_type, target_reference, description)
                            VALUES (src.id, src.workflow_version_id, src.relationship_type, src.target_reference, src.description)
                            """,
                            (rel["id"], rel["workflow_version_id"], rel["relationship_type"], rel["target_reference"], rel.get("description")),
                        )
                    if relationships:
                        tables_updated.append("KNOWLEDGE_STUDIO.workflow_relationships")

                    # 13. Insert References
                    for ref in references:
                        cur.execute(
                            """
                            MERGE INTO KNOWLEDGE_STUDIO.workflow_references AS target
                            USING (SELECT %s AS id, %s AS workflow_version_id, %s AS reference_type, %s AS title, %s AS citation_uri) AS src
                            ON target.id = src.id
                            WHEN MATCHED THEN UPDATE SET citation_uri = src.citation_uri
                            WHEN NOT MATCHED THEN INSERT (id, workflow_version_id, reference_type, title, citation_uri)
                            VALUES (src.id, src.workflow_version_id, src.reference_type, src.title, src.citation_uri)
                            """,
                            (ref["id"], ref["workflow_version_id"], ref["reference_type"], ref["title"], ref["citation_uri"]),
                        )
                    if references:
                        tables_updated.append("KNOWLEDGE_STUDIO.workflow_references")

                    # 14. Insert Role Permissions
                    for perm in role_permissions:
                        cur.execute(
                            """
                            MERGE INTO KNOWLEDGE_STUDIO.workflow_role_permissions AS target
                            USING (SELECT %s AS id, %s AS workflow_version_id, %s AS role_name, %s AS required_permissions, %s AS experience_level, %s AS required_certifications, %s AS language_code, %s AS department_id) AS src
                            ON target.id = src.id
                            WHEN MATCHED THEN UPDATE SET required_permissions = src.required_permissions
                            WHEN NOT MATCHED THEN INSERT (id, workflow_version_id, role_name, required_permissions, experience_level, required_certifications, language_code, department_id)
                            VALUES (src.id, src.workflow_version_id, src.role_name, src.required_permissions, src.experience_level, src.required_certifications, src.language_code, src.department_id)
                            """,
                            (perm["id"], perm["workflow_version_id"], perm["role_name"], perm.get("required_permissions"), perm.get("experience_level"), perm.get("required_certifications"), perm.get("language_code"), perm["department_id"]),
                        )
                    if role_permissions:
                        tables_updated.append("KNOWLEDGE_STUDIO.workflow_role_permissions")

                    # 15. Insert Search Metadata
                    for sm in search_metadata:
                        cur.execute(
                            """
                            MERGE INTO KNOWLEDGE_STUDIO.workflow_search_metadata AS target
                            USING (SELECT %s AS id, %s AS workflow_version_id, %s AS state_id, %s AS department_id, %s AS search_content, %s AS embedding_ref, %s AS status) AS src
                            ON target.id = src.id
                            WHEN MATCHED THEN UPDATE SET search_content = src.search_content, status = 'published'
                            WHEN NOT MATCHED THEN INSERT (id, workflow_version_id, state_id, department_id, search_content, embedding_ref, status)
                            VALUES (src.id, src.workflow_version_id, src.state_id, src.department_id, src.search_content, COALESCE(src.embedding_ref, 'none'), 'published')
                            """,
                            (sm["id"], sm["workflow_version_id"], sm["state_id"], sm["department_id"], sm["search_content"], sm.get("embedding_ref", "none"), sm["status"]),
                        )
                    tables_updated.append("KNOWLEDGE_STUDIO.workflow_search_metadata")

                    import json
                    # 16. Insert Knowledge Documents
                    for doc in documents:
                        tags_json = json.dumps(doc.get("tags", []))
                        labels_json = json.dumps(doc.get("labels", {}))
                        cur.execute(
                            """
                            MERGE INTO WORKMATE_AI.KNOWLEDGE_STUDIO.knowledge_documents AS target
                            USING (SELECT %s AS id, %s AS workflow_id, %s AS workflow_version_id, %s AS document_name, %s AS original_filename,
                                          %s AS stage_uri, %s AS relative_path, %s AS directory, %s AS extension, %s AS mime_type,
                                          %s AS file_size_bytes, %s AS md5_hash, %s AS sha256_hash, %s AS compiler_version, %s AS parser_version,
                                          %s AS source_type, %s AS language_code, %s AS author, %s AS reviewer, %s AS approval_status,
                                          PARSE_JSON(%s) AS tags, PARSE_JSON(%s) AS labels, %s AS description) AS src
                            ON target.id = src.id
                            WHEN MATCHED THEN UPDATE SET document_name = src.document_name, updated_at = CURRENT_TIMESTAMP()
                            WHEN NOT MATCHED THEN INSERT (id, workflow_id, workflow_version_id, document_name, original_filename, stage_uri, relative_path, directory, extension, mime_type, file_size_bytes, md5_hash, sha256_hash, compiler_version, parser_version, source_type, language_code, author, reviewer, approval_status, tags, labels, description)
                            VALUES (src.id, src.workflow_id, src.workflow_version_id, src.document_name, src.original_filename, src.stage_uri, src.relative_path, src.directory, src.extension, src.mime_type, src.file_size_bytes, src.md5_hash, src.sha256_hash, src.compiler_version, src.parser_version, src.source_type, src.language_code, src.author, src.reviewer, src.approval_status, src.tags, src.labels, src.description)
                            """,
                            (doc["id"], doc["workflow_id"], doc["workflow_version_id"], doc["document_name"], doc["original_filename"], doc["stage_uri"], doc["relative_path"], doc["directory"], doc["extension"], doc["mime_type"], doc["file_size_bytes"], doc.get("md5_hash"), doc["sha256_hash"], doc["compiler_version"], doc["parser_version"], doc["source_type"], doc["language_code"], doc.get("author"), doc.get("reviewer"), doc["approval_status"], tags_json, labels_json, doc.get("description")),
                        )
                    if documents:
                        tables_updated.append("WORKMATE_AI.KNOWLEDGE_STUDIO.knowledge_documents")

                    # 17. Insert Knowledge Document Contents
                    for cont in contents:
                        cur.execute(
                            """
                            MERGE INTO WORKMATE_AI.KNOWLEDGE_STUDIO.knowledge_document_contents AS target
                            USING (SELECT %s AS id, %s AS document_id, %s AS workflow_version_id, %s AS raw_markdown, %s AS normalized_markdown,
                                          %s AS frontmatter_yaml, PARSE_JSON(%s) AS frontmatter_json, %s AS body_markdown,
                                          PARSE_JSON(%s) AS sections_json, PARSE_JSON(%s) AS tables_json, PARSE_JSON(%s) AS code_blocks_json,
                                          PARSE_JSON(%s) AS images_json, PARSE_JSON(%s) AS links_json) AS src
                            ON target.id = src.id
                            WHEN MATCHED THEN UPDATE SET raw_markdown = src.raw_markdown
                            WHEN NOT MATCHED THEN INSERT (id, document_id, workflow_version_id, raw_markdown, normalized_markdown, frontmatter_yaml, frontmatter_json, body_markdown, sections_json, tables_json, code_blocks_json, images_json, links_json)
                            VALUES (src.id, src.document_id, src.workflow_version_id, src.raw_markdown, src.normalized_markdown, src.frontmatter_yaml, src.frontmatter_json, src.body_markdown, src.sections_json, src.tables_json, src.code_blocks_json, src.images_json, src.links_json)
                            """,
                            (cont["id"], cont["document_id"], cont["workflow_version_id"], cont["raw_markdown"], cont["normalized_markdown"], cont.get("frontmatter_yaml"), json.dumps(cont.get("frontmatter_json", {})), cont["body_markdown"], json.dumps(cont.get("sections_json", [])), json.dumps(cont.get("tables_json", [])), json.dumps(cont.get("code_blocks_json", [])), json.dumps(cont.get("images_json", [])), json.dumps(cont.get("links_json", []))),
                        )
                    if contents:
                        tables_updated.append("WORKMATE_AI.KNOWLEDGE_STUDIO.knowledge_document_contents")

                    # 18. Insert Knowledge Document AI Metadata
                    for ai in ai_metadata:
                        cur.execute(
                            """
                            MERGE INTO WORKMATE_AI.KNOWLEDGE_STUDIO.knowledge_document_ai_metadata AS target
                            USING (SELECT %s AS id, %s AS document_id, %s AS workflow_version_id, %s AS reading_time_minutes, %s AS word_count,
                                          %s AS sentence_count, %s AS paragraph_count, %s AS complexity_score, %s AS risk_score, %s AS summary,
                                          PARSE_JSON(%s) AS keywords, PARSE_JSON(%s) AS entities, %s AS language_detected, %s AS embedding_model,
                                          %s AS embedding_version, %s AS chunk_count, %s AS average_chunk_size, %s AS embedding_status,
                                          %s AS evaluation_score, %s AS confidence_score) AS src
                            ON target.id = src.id
                            WHEN MATCHED THEN UPDATE SET summary = src.summary, embedding_status = src.embedding_status
                            WHEN NOT MATCHED THEN INSERT (id, document_id, workflow_version_id, reading_time_minutes, word_count, sentence_count, paragraph_count, complexity_score, risk_score, summary, keywords, entities, language_detected, embedding_model, embedding_version, chunk_count, average_chunk_size, embedding_status, evaluation_score, confidence_score)
                            VALUES (src.id, src.document_id, src.workflow_version_id, src.reading_time_minutes, src.word_count, src.sentence_count, src.paragraph_count, src.complexity_score, src.risk_score, src.summary, src.keywords, src.entities, src.language_detected, src.embedding_model, src.embedding_version, src.chunk_count, src.average_chunk_size, src.embedding_status, src.evaluation_score, src.confidence_score)
                            """,
                            (ai["id"], ai["document_id"], ai["workflow_version_id"], ai["reading_time_minutes"], ai["word_count"], ai["sentence_count"], ai["paragraph_count"], ai["complexity_score"], ai["risk_score"], ai.get("summary"), json.dumps(ai.get("keywords", [])), json.dumps(ai.get("entities", {})), ai["language_detected"], ai["embedding_model"], ai["embedding_version"], ai["chunk_count"], ai["average_chunk_size"], ai["embedding_status"], ai["evaluation_score"], ai["confidence_score"]),
                        )
                    if ai_metadata:
                        tables_updated.append("WORKMATE_AI.KNOWLEDGE_STUDIO.knowledge_document_ai_metadata")

                    # 19. Insert Knowledge Document Chunks
                    for chk in chunks:
                        cur.execute(
                            """
                            MERGE INTO WORKMATE_AI.KNOWLEDGE_STUDIO.knowledge_document_chunks AS target
                            USING (SELECT %s AS id, %s AS document_id, %s AS workflow_version_id, %s AS state_id, %s AS step_id,
                                          %s AS chunk_order, %s AS character_count, %s AS token_count, %s AS chunk_content, %s AS embedding_ref,
                                          %s AS vector_status, %s AS chunk_hash, %s AS chunk_type, %s AS section_name) AS src
                            ON target.id = src.id
                            WHEN MATCHED THEN UPDATE SET chunk_content = src.chunk_content
                            WHEN NOT MATCHED THEN INSERT (id, document_id, workflow_version_id, state_id, step_id, chunk_order, character_count, token_count, chunk_content, embedding_ref, vector_status, chunk_hash, chunk_type, section_name)
                            VALUES (src.id, src.document_id, src.workflow_version_id, src.state_id, src.step_id, src.chunk_order, src.character_count, src.token_count, src.chunk_content, src.embedding_ref, src.vector_status, src.chunk_hash, src.chunk_type, src.section_name)
                            """,
                            (chk["id"], chk["document_id"], chk["workflow_version_id"], chk.get("state_id"), chk.get("step_id"), chk["chunk_order"], chk["character_count"], chk["token_count"], chk["chunk_content"], chk["embedding_ref"], chk["vector_status"], chk["chunk_hash"], chk["chunk_type"], chk.get("section_name")),
                        )
                    if chunks:
                        tables_updated.append("WORKMATE_AI.KNOWLEDGE_STUDIO.knowledge_document_chunks")

                    # 20. Insert Knowledge Document Lineage
                    for lin in lineage:
                        cur.execute(
                            """
                            MERGE INTO WORKMATE_AI.KNOWLEDGE_STUDIO.knowledge_document_lineage AS target
                            USING (SELECT %s AS id, %s AS document_id, %s AS workflow_version_id, %s AS stage_file_uri, %s AS source_markdown_hash,
                                          %s AS parser_name, %s AS ast_hash, %s AS compiler_name, %s AS loader_name, %s AS status, %s AS executed_by, %s AS execution_notes) AS src
                            ON target.id = src.id
                            WHEN MATCHED THEN UPDATE SET status = src.status
                            WHEN NOT MATCHED THEN INSERT (id, document_id, workflow_version_id, stage_file_uri, source_markdown_hash, parser_name, ast_hash, compiler_name, loader_name, status, executed_by, execution_notes)
                            VALUES (src.id, src.document_id, src.workflow_version_id, src.stage_file_uri, src.source_markdown_hash, src.parser_name, src.ast_hash, src.compiler_name, src.loader_name, src.status, src.executed_by, src.execution_notes)
                            """,
                            (lin["id"], lin["document_id"], lin["workflow_version_id"], lin["stage_file_uri"], lin["source_markdown_hash"], lin["parser_name"], lin["ast_hash"], lin["compiler_name"], lin["loader_name"], lin["status"], lin["executed_by"], lin.get("execution_notes")),
                        )
                    if lineage:
                        tables_updated.append("WORKMATE_AI.KNOWLEDGE_STUDIO.knowledge_document_lineage")

                    cur.execute(
                        """
                        SELECT status,
                               (SELECT COUNT(*) FROM KNOWLEDGE_STUDIO.workflow_states WHERE workflow_version_id = %s),
                               (SELECT COUNT(*) FROM KNOWLEDGE_STUDIO.workflow_search_metadata WHERE workflow_version_id = %s)
                        FROM KNOWLEDGE_STUDIO.workflow_versions
                        WHERE id = %s
                        """,
                        (ver["id"], ver["id"], ver["id"]),
                    )
                    invariant = cur.fetchone()
                    if (
                        not invariant
                        or str(invariant[0]).lower() != "published"
                        or int(invariant[1]) != len(states)
                        or int(invariant[2]) != len(search_metadata)
                    ):
                        raise OWDLoaderException("Post-load workflow invariants failed; transaction will be rolled back.")
                    cur.execute("COMMIT")

            logger.info(f"[LOADER SUCCESS] Successfully loaded OWD v1.1 '{wf['workflow_code']}' into Snowflake ({len(set(tables_updated))} tables updated).")
            return LoadResult(
                success=True,
                workflow_id=wf["id"],
                version_id=ver["id"],
                tables_updated=list(set(tables_updated)),
            )

        except Exception as e:
            if conn is not None:
                try:
                    with conn.cursor() as rollback_cur:
                        rollback_cur.execute("ROLLBACK")
                except Exception as rollback_exc:
                    logger.debug("Loader rollback was already handled by the connection boundary: %s", rollback_exc)
            logger.error(f"[LOADER ERROR] Failed to load compiled workflow into Snowflake: {str(e)}")
            raise OWDLoaderException(message=f"Failed to persist OWD workflow in Snowflake: {str(e)}") from e
