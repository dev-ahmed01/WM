"""Step Parser Sub-Parser Module (Section 5).

Parses atomic Step Definitions:
  Step ID, Sequence Number, Action, Expected Outcome, Safety Note,
  Evidence Required, Estimated Time, Retry Policy, Completion Criteria,
  Common Failure, Recovery Action.
"""

import yaml
import logging
from typing import Dict, Any, List
from app.compiler.models import Step, AIGuidance
from app.compiler.parsers.ai_conversation_parser import AIConversationParser
from app.compiler.parsers.document_parser import RawASTNode
from app.compiler.utils import sanitize_code

logger = logging.getLogger("compiler.parser.step")

class StepParser:
    """Parses Section 5: Step Definitions from AST Nodes."""

    @staticmethod
    def parse_step_nodes(nodes: List[RawASTNode], state_key: str, start_index: int = 0) -> List[Step]:
        """Parses list items and structured :::step directives from AST nodes."""
        steps: List[Step] = []
        step_counter = start_index + 1

        for node in nodes:
            # 1. Parse structured :::step directive blocks
            if node.node_type == "DIRECTIVE_BLOCK" and node.metadata.get("directive_type") == "step":
                st_code = sanitize_code(node.metadata.get("directive_code") or f"STEP_{state_key}_{step_counter}", prefix="STEP")
                st_dict: Dict[str, Any] = {}
                try:
                    parsed = yaml.safe_load(node.content)
                    if isinstance(parsed, dict):
                        st_dict.update(parsed)
                except Exception:
                    for line in node.content.splitlines():
                        if ":" in line:
                            k, v = line.split(":", 1)
                            st_dict[k.strip().lower()] = v.strip().strip('"\'')

                instr = str(st_dict.get("instruction") or st_dict.get("action") or f"Execute step {st_code}")
                conv_layer = AIConversationParser.parse_block(node.content, default_instruction=instr)

                steps.append(
                    Step(
                        step_code=st_code,
                        sequence_number=int(st_dict.get("sequence_number", step_counter)),
                        instruction=instr,
                        action=str(st_dict.get("action", instr)),
                        expected_outcome=str(st_dict.get("expected_outcome", "Step completed successfully")),
                        safety_note=st_dict.get("safety_note"),
                        evidence_required=st_dict.get("evidence_required"),
                        estimated_time=str(st_dict.get("estimated_time", "5 mins")),
                        retry_policy=str(st_dict.get("retry_policy", "MAX_RETRIES_3")),
                        completion_criteria=str(st_dict.get("completion_criteria", "User confirmation")),
                        common_failure=st_dict.get("common_failure"),
                        recovery_action=st_dict.get("recovery_action"),
                        expected_output_type=str(st_dict.get("output_type", "CONFIRMATION")),
                        is_mandatory=bool(st_dict.get("mandatory", True)),
                        ai_conversation=conv_layer,
                        ordinal_index=0,  # Will be set globally
                    )
                )
                step_counter += 1

            # 2. Parse inline list items
            elif node.node_type == "LIST_ITEM":
                if not node.metadata.get("is_checkbox"):
                    continue
                
                clean_line = node.content.strip()
                if not clean_line:
                    continue

                st_code = node.metadata.get("step_code")
                if st_code:
                    st_code = sanitize_code(st_code, prefix="STEP")
                else:
                    st_code = f"STEP_{state_key}_{step_counter}"

                # Avoid duplicate step codes
                if any(st.step_code == st_code for st in steps):
                    continue

                ai_guidance = AIGuidance(
                    prompt_template=f"Assist operator with step: {clean_line}",
                    contextual_instructions=clean_line,
                )
                conv_layer = AIConversationParser.parse_block(clean_line, default_instruction=clean_line)

                steps.append(
                    Step(
                        step_code=st_code,
                        sequence_number=step_counter,
                        instruction=clean_line,
                        action=clean_line,
                        expected_outcome="Step completed successfully",
                        expected_output_type="CONFIRMATION",
                        is_mandatory=True,
                        ai_guidance=ai_guidance,
                        ai_conversation=conv_layer,
                        ordinal_index=0,  # Will be set globally
                    )
                )
                step_counter += 1

            # 3. Notice we COMPLETELY ignore "PARAGRAPH" and "HEADER" nodes here!
            # This fixes Bug 1 & 10: Metadata in paragraphs will no longer be parsed as executable steps.

        return steps
