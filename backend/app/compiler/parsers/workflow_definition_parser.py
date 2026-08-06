"""Workflow Definition Parser Sub-Parser Module (Section 3).

Parses Workflow Definition:
  Workflow Objective, Business Goal, Entry Conditions, Exit Conditions,
  Previous Workflow, Next Workflow, Blocking Workflows, Optional Workflows,
  Expected Business Outcome.
"""

import re
import yaml
import logging
from typing import Dict, Any, List
from app.compiler.models import WorkflowDefinition

logger = logging.getLogger("compiler.parser.workflow_definition")


class WorkflowDefinitionParser:
    """Parses Section 3: Workflow Definition."""

    @staticmethod
    def parse(markdown_text: str, default_title: str = "") -> WorkflowDefinition:
        """Parses Section 3 workflow definition."""
        wf_dict: Dict[str, Any] = {}

        # 1. Check :::workflow_definition block
        directive_match = re.search(r":::workflow_definition\s*\n(.*?)\n:::", markdown_text, re.DOTALL | re.IGNORECASE)
        if directive_match:
            try:
                parsed_yaml = yaml.safe_load(directive_match.group(1))
                if isinstance(parsed_yaml, dict):
                    wf_dict.update(parsed_yaml)
            except Exception as exc:
                logger.warning(f"Failed to parse :::workflow_definition block: {exc}")

        # 2. Check '# Workflow Definition' section
        sec_match = re.search(r"#\s*(?:3\s*)?Workflow Definition\s*\n(.*?)(?=\n#|\Z)", markdown_text, re.DOTALL | re.IGNORECASE)
        if sec_match:
            for line in sec_match.group(1).splitlines():
                line_trim = line.strip().lstrip("-* ").strip()
                if ":" in line_trim:
                    k, v = line_trim.split(":", 1)
                    k_clean = k.strip().lower().replace(" ", "_")
                    v_clean = v.strip().strip('"\'')
                    if k_clean not in wf_dict or not wf_dict[k_clean]:
                        wf_dict[k_clean] = v_clean

        def parse_list(val: Any) -> List[str]:
            if isinstance(val, list):
                return [str(x).strip() for x in val if str(x).strip()]
            if isinstance(val, str) and val.strip():
                return [x.strip() for x in val.split(",") if x.strip()]
            return []

        return WorkflowDefinition(
            workflow_objective=str(wf_dict.get("workflow_objective") or wf_dict.get("objective") or f"Execute workflow for {default_title}"),
            business_goal=str(wf_dict.get("business_goal") or wf_dict.get("goal") or "Ensure process compliance"),
            entry_conditions=parse_list(wf_dict.get("entry_conditions")),
            exit_conditions=parse_list(wf_dict.get("exit_conditions")),
            previous_workflow=wf_dict.get("previous_workflow"),
            next_workflow=wf_dict.get("next_workflow"),
            blocking_workflows=parse_list(wf_dict.get("blocking_workflows")),
            optional_workflows=parse_list(wf_dict.get("optional_workflows")),
            expected_business_outcome=str(wf_dict.get("expected_business_outcome", "Process Completed Successfully")),
        )
