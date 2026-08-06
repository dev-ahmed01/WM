"""Decision Parser Sub-Parser Module (Section 7).

Parses Decision Engine nodes & options:
  Decision ID, Question, Possible Answers, Next State, Next Step,
  Alternative Path, Business Rule, Escalation Workflow.
Generates deterministic workflow transitions for decision branches.
"""

import re
import yaml
import logging
from typing import Dict, Any, List, Tuple, TYPE_CHECKING
from app.compiler.models import DecisionNode, DecisionOption, Transition
from app.compiler.utils import sanitize_code

if TYPE_CHECKING:
    from app.compiler.parsers.document_parser import RawASTNode

logger = logging.getLogger("compiler.parser.decision")


class DecisionParser:
    """Parses Section 7: Decision Engine Nodes."""

    @staticmethod
    def parse_decision_nodes(
        nodes: List['RawASTNode'],
        state_key: str,
    ) -> Tuple[List[DecisionNode], List[Transition]]:
        """Parses decision blocks from AST nodes and generates deterministic state transitions."""
        decisions: List[DecisionNode] = []
        generated_transitions: List[Transition] = []

        for node in nodes:
            if node.node_type == "DIRECTIVE_BLOCK" and node.metadata.get("directive_type") == "decision":
                dec_code = sanitize_code(node.metadata.get("directive_code") or f"DEC_{state_key}", prefix="DEC")
                content = node.content
                dec_dict: Dict[str, Any] = {}
                options: List[DecisionOption] = []

                try:
                    parsed = yaml.safe_load(content)
                    if isinstance(parsed, dict):
                        dec_dict.update(parsed)
                except Exception:
                    for line in content.splitlines():
                        if ":" in line:
                            k, v = line.split(":", 1)
                            dec_dict[k.strip().lower()] = v.strip().strip('"\'')

                q_text = str(dec_dict.get("question") or dec_dict.get("prompt") or f"Evaluate decision for {state_key}")

                # Parse options
                raw_options = dec_dict.get("options") or dec_dict.get("possible_answers") or []
                if isinstance(raw_options, list):
                    for idx, opt in enumerate(raw_options, 1):
                        if isinstance(opt, dict):
                            opt_code = sanitize_code(opt.get("option_code") or f"OPT_{idx}", prefix="OPT")
                            opt_label = str(opt.get("label") or opt.get("option_label") or f"Option {idx}")
                            target_state = str(opt.get("next_state") or opt.get("target_state_key") or "STATE_END")
                            next_step = opt.get("next_step")
                        else:
                            opt_code = f"OPT_{idx}"
                            opt_label = str(opt)
                            target_state = "STATE_END"
                            next_step = None

                        options.append(
                            DecisionOption(
                                option_code=opt_code,
                                option_label=opt_label,
                                target_state_key=target_state,
                                next_step_code=next_step,
                            )
                        )
                        # Generate deterministic transition for option branch
                        generated_transitions.append(
                            Transition(
                                from_state_key=state_key,
                                to_state_key=target_state,
                                condition_type="DECISION_OPTION",
                                condition_expression=opt_code,
                                priority=10,
                            )
                        )

                decisions.append(
                    DecisionNode(
                        decision_code=dec_code,
                        question=q_text,
                        options=options,
                        alternative_path=dec_dict.get("alternative_path"),
                        business_rule=dec_dict.get("business_rule"),
                        escalation_workflow=dec_dict.get("escalation_workflow"),
                    )
                )

        return decisions, generated_transitions
