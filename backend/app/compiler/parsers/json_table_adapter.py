"""Adapter for the JSON-block and Markdown-table OWD authoring dialect."""

import json
import re
from typing import Any, Dict, List

import yaml

from app.compiler.utils import sanitize_code


class JsonTableOWDAdapter:
    """Convert current authoring files to canonical directives before parsing."""

    @staticmethod
    def is_supported_format(markdown_text: str) -> bool:
        return bool(
            re.search(r"^##\s*1\.\s*Document Metadata\s*$", markdown_text, re.MULTILINE | re.IGNORECASE)
            and re.search(r"^##\s*4\.\s*Workflow States\s*$", markdown_text, re.MULTILINE | re.IGNORECASE)
            and re.search(r"^##\s*5\.\s*Step Definitions\s*$", markdown_text, re.MULTILINE | re.IGNORECASE)
            and '"step_id"' in markdown_text
        )

    @staticmethod
    def _section(markdown_text: str, number: int, title: str) -> str:
        match = re.search(
            rf"^##\s*{number}\.\s*{re.escape(title)}\s*$\n(.*?)(?=^##\s*\d+\.|\Z)",
            markdown_text,
            re.MULTILINE | re.DOTALL | re.IGNORECASE,
        )
        return match.group(1).strip() if match else ""

    @staticmethod
    def _json_blocks(section: str) -> List[Dict[str, Any]]:
        blocks: List[Dict[str, Any]] = []
        for match in re.finditer(r"```json\s*\n(.*?)\n```", section, re.DOTALL | re.IGNORECASE):
            value = json.loads(match.group(1))
            if isinstance(value, dict):
                blocks.append(value)
        return blocks

    @staticmethod
    def _table(section: str) -> List[Dict[str, str]]:
        lines = [line.strip() for line in section.splitlines() if line.strip().startswith("|")]
        if len(lines) < 3:
            return []
        headers = [cell.strip() for cell in lines[0].strip("|").split("|")]
        rows: List[Dict[str, str]] = []
        for line in lines[2:]:
            values = [cell.strip() for cell in line.strip("|").split("|")]
            if len(values) == len(headers):
                rows.append(dict(zip(headers, values)))
        return rows

    @staticmethod
    def _clean_reference(value: Any) -> str:
        text = str(value or "").strip()
        return text.split(" ", 1)[0] if text else ""

    @staticmethod
    def _decision_target(
        value: Any,
        workflow_code: str,
        local_state_ids: List[str],
    ) -> tuple[str, Dict[str, str] | None]:
        """Resolve local targets and turn cross-SOP routes into terminal handoffs."""
        reference = str(value or "").strip()
        if not reference:
            return "STATE_END", None

        target_workflow = ""
        target_state = reference
        if ":" in reference:
            target_workflow, target_state = (
                part.strip() for part in reference.split(":", 1)
            )

        normalized_workflow = sanitize_code(workflow_code, prefix="WORKFLOW")
        referenced_workflow = sanitize_code(target_workflow, prefix="WORKFLOW")
        local_states = {
            sanitize_code(state_id, prefix="STATE") for state_id in local_state_ids
        }
        normalized_state = sanitize_code(target_state, prefix="STATE")
        if (
            not target_workflow
            or referenced_workflow == normalized_workflow
        ) and normalized_state in local_states:
            return normalized_state, None

        handoff_key = sanitize_code(f"HANDOFF_{reference}", prefix="STATE")
        return handoff_key, {
            "state_key": handoff_key,
            "workflow": target_workflow or reference,
            "state": target_state if target_workflow else "",
            "reference": reference,
        }

    @classmethod
    def adapt(cls, markdown_text: str, department_id: str = "") -> str:
        if not cls.is_supported_format(markdown_text):
            return markdown_text

        metadata = cls._json_blocks(cls._section(markdown_text, 1, "Document Metadata"))[0]
        retrieval_blocks = cls._json_blocks(cls._section(markdown_text, 2, "AI Retrieval Metadata"))
        retrieval = retrieval_blocks[0] if retrieval_blocks else {}
        definition_blocks = cls._json_blocks(cls._section(markdown_text, 3, "Workflow Definition"))
        definition = definition_blocks[0] if definition_blocks else {}
        state_rows = cls._table(cls._section(markdown_text, 4, "Workflow States"))
        step_section = cls._section(markdown_text, 5, "Step Definitions")

        steps_by_state: Dict[str, List[Dict[str, Any]]] = {}
        current_state = ""
        for part in re.split(r"(?=^###\s+State\s+)", step_section, flags=re.MULTILINE):
            state_match = re.match(r"^###\s+State\s+([A-Za-z0-9_-]+)", part)
            if state_match:
                current_state = state_match.group(1)
            if current_state:
                steps_by_state.setdefault(current_state, []).extend(cls._json_blocks(part))

        state_ids = [row.get("State ID", "").strip() for row in state_rows]
        state_ids = [state_id for state_id in state_ids if state_id]
        workflow_code = str(
            metadata.get("sop_id") or definition.get("workflow_id") or "WORKFLOW"
        )
        handoff_states: Dict[str, Dict[str, str]] = {}
        step_to_state = {
            str(step.get("step_id")): state_id
            for state_id, steps in steps_by_state.items()
            for step in steps
            if step.get("step_id")
        }

        frontmatter = {
            "spec_version": "1.1",
            "sop_id": metadata.get("sop_id") or definition.get("workflow_id"),
            "version": metadata.get("version", "1.1.0"),
            "department": department_id or metadata.get("department", "dept_operations"),
            "category": metadata.get("category", "OPERATIONAL_SOP"),
            "owner": metadata.get("owner", "System Admin"),
            "priority": str(metadata.get("priority", "MEDIUM")).upper(),
            "difficulty": str(metadata.get("difficulty", "INTERMEDIATE")).upper(),
            "estimated_duration": metadata.get("estimated_duration", "30 mins"),
            "roles_allowed": metadata.get("roles_allowed", []),
            "required_equipment": metadata.get("required_equipment", []),
            "dependencies": [
                item.get("sop_id") if isinstance(item, dict) else item
                for item in metadata.get("dependencies", [])
            ],
            "related_sops": metadata.get("related_sops", []),
            "review_cycle": metadata.get("review_cycle", "ANNUAL"),
            "effective_date": metadata.get("effective_date", "2026-01-01"),
        }
        title_match = re.search(r"^#\s+SOP:\s*(.+)$", markdown_text, re.MULTILINE | re.IGNORECASE)
        title = title_match.group(1).strip() if title_match else str(frontmatter["sop_id"])
        output = ["---", yaml.safe_dump(frontmatter, sort_keys=False).strip(), "---", "", f"# {frontmatter['sop_id']}: {title}"]

        output.extend(["", "# 2 AI Retrieval Metadata"])
        retrieval_mapping = {
            "keywords": retrieval.get("keywords", []),
            "synonyms": retrieval.get("synonyms", []),
            "search_phrases": retrieval.get("alternative_user_phrases", []),
            "search_queries": retrieval.get("search_queries", []),
            "business_process": retrieval.get("business_process", "Operational Workflow"),
            "equipment": retrieval.get("related_equipment", []),
            "workflow_tags": retrieval.get("tags", []),
        }
        for key, value in retrieval_mapping.items():
            output.append(f"{key}: {', '.join(map(str, value)) if isinstance(value, list) else value}")

        output.extend(["", "# 3 Workflow Definition"])
        for key in (
            "workflow_objective", "business_goal", "entry_conditions", "exit_conditions",
            "previous_workflow", "next_workflow", "blocking_workflows", "optional_workflows",
            "expected_business_outcome",
        ):
            value = definition.get(key)
            if value is not None:
                output.append(f"{key}: {', '.join(map(str, value)) if isinstance(value, list) else value}")

        output.extend(["", "# 4 Workflow States & Steps"])
        for index, row in enumerate(state_rows):
            state_id = row.get("State ID", "").strip()
            if not state_id:
                continue
            state_steps = steps_by_state.get(state_id, [])
            has_decision = any(isinstance(step.get("decision"), dict) for step in state_steps)
            state_type = "DECISION" if has_decision else "ATOMIC_STEP"
            is_terminal = index == len(state_rows) - 1
            props = {
                "type": state_type,
                "is_initial": "true" if index == 0 else "false",
                "is_terminal": "true" if is_terminal else "false",
                "purpose": row.get("Purpose", ""),
                "entry_condition": row.get("Entry Condition", ""),
                "exit_condition": row.get("Exit Condition", ""),
                "responsible_role": row.get("Responsible Role", "Employee"),
                "expected_duration": row.get("Expected Duration", "10 mins"),
                "business_objective": row.get("Business Objective", ""),
            }
            encoded_props = " ".join(f'{key}={json.dumps(str(value))}' for key, value in props.items())
            output.extend(["", f"::state[{state_id}]{{{encoded_props}}}", f"## State {index + 1}: {row.get('State Name', state_id)}"])

            transition_targets: List[str] = []
            for step in state_steps:
                step_id = str(step.get("step_id") or f"{state_id}-STEP")
                retry_allowed = bool(step.get("retry_allowed", True))
                retry_count = int(step.get("maximum_retry_count", 3) or 0)
                retry_policy = "NO_RETRY" if not retry_allowed or retry_count == 0 else f"MAX_RETRIES_{retry_count}"
                if retry_policy not in {"MAX_RETRIES_1", "MAX_RETRIES_3", "MAX_RETRIES_5", "NO_RETRY"}:
                    retry_policy = "MAX_RETRIES_3"
                step_payload = {
                    "sequence_number": step.get("sequence_number", 1),
                    "instruction": step.get("action", ""),
                    "action": step.get("action", ""),
                    "expected_outcome": step.get("expected_outcome", "Step completed successfully"),
                    "safety_note": step.get("safety_note"),
                    "evidence_required": step.get("evidence_required"),
                    "estimated_time": step.get("estimated_time", "5 mins"),
                    "retry_policy": retry_policy,
                    "completion_criteria": step.get("completion_criteria", "User confirmation"),
                    "common_failure": step.get("common_failure"),
                    "recovery_action": step.get("recovery_action"),
                }
                output.extend(["", f":::step[{step_id}]", yaml.safe_dump(step_payload, sort_keys=False).strip()])
                conversation = step.get("ai_conversation_layer")
                if isinstance(conversation, dict):
                    conversation = dict(conversation)
                    if conversation.get("question_ai_should_ask") is None:
                        conversation["question_ai_should_ask"] = f"Have you completed: {step.get('action', '')}?"
                    output.extend([":::ai_conversation", yaml.safe_dump(conversation, sort_keys=False).strip(), ":::"])
                output.append(":::")

                decision = step.get("decision")
                if isinstance(decision, dict):
                    next_states = decision.get("next_state", {})
                    next_steps = decision.get("next_step", {})
                    options = []
                    for option in decision.get("possible_answers", []):
                        answer_value = str(option.get("answer_value", "option"))
                        target_key, handoff = cls._decision_target(
                            next_states.get(answer_value, ""),
                            workflow_code,
                            state_ids,
                        )
                        if handoff:
                            handoff_states[target_key] = handoff
                        options.append({
                            "option_code": answer_value,
                            "option_label": option.get("label", answer_value),
                            "next_state": target_key,
                            "next_step": next_steps.get(answer_value),
                        })
                    decision_payload = {
                        "question": decision.get("decision_question", "Choose the observed outcome."),
                        "options": options,
                        "alternative_path": json.dumps(decision.get("alternative_path", {})),
                        "business_rule": decision.get("business_rule"),
                        "escalation_workflow": decision.get("escalation_workflow"),
                    }
                    output.extend(["", f":::decision[{decision.get('decision_id', 'DECISION')}]", yaml.safe_dump(decision_payload, sort_keys=False).strip(), ":::"])
                elif step.get("next_step"):
                    next_step = str(step["next_step"]).split("/", 1)[0].strip()
                    target_state = step_to_state.get(next_step)
                    if target_state and target_state != state_id and target_state not in transition_targets:
                        transition_targets.append(target_state)

            if not has_decision and not is_terminal:
                target = transition_targets[0] if transition_targets else state_ids[index + 1]
                output.extend(["", f'::transition{{to="{target}" condition="ALWAYS"}}'])

        for handoff in handoff_states.values():
            destination = handoff["workflow"]
            if handoff["state"]:
                destination = f"{destination} at {handoff['state']}"
            props = {
                "type": "END",
                "is_initial": "false",
                "is_terminal": "true",
                "purpose": f"Continue the governed process in {destination}.",
                "entry_condition": "Selected as the verified workflow outcome.",
                "exit_condition": "This workflow hands control to the referenced SOP.",
                "responsible_role": "Employee",
                "expected_duration": "0 mins",
                "business_objective": "Preserve an explicit cross-SOP workflow handoff.",
            }
            encoded_props = " ".join(
                f'{key}={json.dumps(str(value))}' for key, value in props.items()
            )
            output.extend([
                "",
                f"::state[{handoff['state_key']}]{{{encoded_props}}}",
                f"## Handoff: {handoff['reference']}",
            ])

        user_blocks = cls._json_blocks(cls._section(markdown_text, 8, "User Context"))
        if user_blocks:
            user = user_blocks[0]
            output.extend(["", "# 8 User Context"])
            output.append(f"roles: {', '.join(map(str, user.get('applicable_roles', [])))}")
            output.append(f"experience_levels: {', '.join(map(str, user.get('experience_level_supported', [])))}")
            output.append(f"certifications: {', '.join(map(str, user.get('required_certification', [])))}")
            output.append("supported_languages: en-US")
            output.append(f"department: {department_id or user.get('department', metadata.get('department', 'dept_operations'))}")

        analytics_rows = cls._table(cls._section(markdown_text, 9, "Analytics Events"))
        if analytics_rows:
            analytics_events = []
            analytics_kpis: List[str] = []
            for row in analytics_rows:
                event_name = row.get("Event", "").strip().strip("*_` ")
                trigger = row.get("Trigger", "").strip()
                if event_name.lower() == "kpis":
                    analytics_kpis.extend(
                        value.strip()
                        for value in trigger.split(";")
                        if value.strip()
                    )
                    continue
                if event_name:
                    analytics_events.append({
                        "name": event_name,
                        "trigger": trigger,
                        "kpis": [row.get("Consumed By", "").strip()],
                    })
            output.extend([
                "",
                ":::analytics",
                yaml.safe_dump(
                    {"events": analytics_events, "kpis": analytics_kpis},
                    sort_keys=False,
                ).strip(),
                ":::",
            ])

        relationship_blocks = cls._json_blocks(cls._section(markdown_text, 10, "Knowledge Relationships"))
        if relationship_blocks:
            source_relationships = relationship_blocks[0]
            canonical_relationships = {
                "parent_sop": source_relationships.get("parent_sop") or source_relationships.get("parent_workflow"),
                "child_sops": source_relationships.get("child_sops") or source_relationships.get("child_workflows", []),
                "related_sops": source_relationships.get("related_sops", []),
                "previous_sop": source_relationships.get("previous_sop") or source_relationships.get("predecessor_sop"),
                "next_sop": source_relationships.get("next_sop") or source_relationships.get("successor_sop") or source_relationships.get("next_sops", []),
                "escalation_sop": source_relationships.get("escalation_sop") or source_relationships.get("escalation_sops", []),
                "exception_sop": source_relationships.get("exception_sop") or source_relationships.get("exception_sops", []),
                "referenced_equipment": source_relationships.get("referenced_equipment", []),
                "referenced_documents": source_relationships.get("referenced_documents", []),
                "referenced_policies": source_relationships.get("referenced_policies", []),
            }
            canonical_relationships = {
                key: value for key, value in canonical_relationships.items() if value
            }
            output.extend(["", ":::relationships", yaml.safe_dump(canonical_relationships, sort_keys=False).strip(), ":::"])

        reference_rows = cls._table(cls._section(markdown_text, 11, "References"))
        if reference_rows:
            reference_map = {
                row.get("Field", "").strip().lower().replace(" ", "_"): row.get("Value", "")
                for row in reference_rows
            }
            aliases = {"official_documentation_url": "official_documentation_url", "relevant_documentation_section": "documentation_sections"}
            references = {aliases.get(key, key): value for key, value in reference_map.items()}
            output.extend(["", ":::references", yaml.safe_dump(references, sort_keys=False).strip(), ":::"])

        return "\n".join(output).strip() + "\n"
