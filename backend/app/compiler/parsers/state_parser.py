"""State Parser Sub-Parser Module (Section 4).

Parses Workflow States & graph nodes using the Document AST.
"""

import re
import logging
from typing import Dict, Any, List
from app.compiler.models import (
    State,
    Transition,
    BusinessRule,
    SafetyRule,
    ValidationRule,
    EvidenceSpec,
)
from app.compiler.parsers.step_parser import StepParser
from app.compiler.parsers.decision_parser import DecisionParser
from app.compiler.parsers.document_parser import RawASTNode
from app.compiler.utils import sanitize_code

logger = logging.getLogger("compiler.parser.state")

class StateParser:
    """Parses Section 4: Workflow States using AST nodes."""

    @staticmethod
    def parse_states(nodes: List[RawASTNode]) -> List[State]:
        """Parses state boundaries and contents from AST nodes."""
        states: List[State] = []
        
        # Group nodes into states
        state_blocks: List[Dict[str, Any]] = []
        current_state: Dict[str, Any] = {"key": None, "title": None, "props": {}, "nodes": []}
        
        for node in nodes:
            if node.node_type == "INLINE_DIRECTIVE" and node.metadata.get("directive_type") == "state":
                if current_state["nodes"] or (current_state["key"] and current_state["key"] != "STATE_START"):
                    state_blocks.append(current_state)
                
                s_code = node.metadata.get("directive_code", f"STATE_{len(state_blocks)+1}")
                s_key = sanitize_code(s_code, prefix="STATE")
                
                # Prevent duplicate state keys
                original_key = s_key
                suffix = 2
                while any(b["key"] == s_key for b in state_blocks):
                    s_key = f"{original_key}_{suffix}"
                    suffix += 1
                
                current_state = {
                    "key": s_key,
                    "title": None,
                    "props": node.metadata.get("properties", {}),
                    "nodes": []
                }
            elif node.node_type == "HEADER" and re.search(r"State\s*\d*:", node.content, re.IGNORECASE):
                # If we just started a state via directive and it's empty, use header as title
                if current_state["key"] and current_state["key"] != "STATE_START" and not current_state["nodes"]:
                    match = re.search(r"State\s*\d*:\s*(.*)", node.content, re.IGNORECASE)
                    if match:
                        current_state["title"] = match.group(1).strip()
                    current_state["nodes"].append(node)
                else:
                    if current_state["nodes"] or (current_state["key"] and current_state["key"] != "STATE_START"):
                        state_blocks.append(current_state)
                        
                    match = re.search(r"State\s*\d*:\s*(.*)", node.content, re.IGNORECASE)
                    s_title = match.group(1).strip() if match else node.content
                    s_code = sanitize_code(s_title.replace(" ", "_").upper(), prefix="STATE")
                    
                    s_key = s_code
                    # Prevent duplicate state keys
                    original_key = s_key
                    suffix = 2
                    while any(b["key"] == s_key for b in state_blocks):
                        s_key = f"{original_key}_{suffix}"
                        suffix += 1
                    
                    current_state = {
                        "key": s_key,
                        "title": s_title,
                        "props": {},
                        "nodes": [node]
                    }
            else:
                if not current_state["key"]:
                    # Default state for docs without explicit states
                    current_state = {
                        "key": "STATE_START",
                        "title": "Operational Execution",
                        "props": {},
                        "nodes": []
                    }
                current_state["nodes"].append(node)
                
        if current_state["nodes"] or current_state["key"]:
            state_blocks.append(current_state)

        if not state_blocks:
            return []

        for i, block in enumerate(state_blocks):
            state_key = block["key"]
            props = block["props"]
            block_nodes: List[RawASTNode] = block["nodes"]
            
            state_title = props.get("title") or block["title"] or state_key.replace("_", " ").title()
            description = props.get("description")
            
            for n in block_nodes:
                if n.node_type == "HEADER" and not block["title"]:
                    state_title = n.content.strip()
                    break

            # Parse steps (StepParser sets sequence_number inside state, ordinal_index globally later)
            steps = StepParser.parse_step_nodes(block_nodes, state_key, start_index=0)
            
            decisions, dec_transitions = DecisionParser.parse_decision_nodes(block_nodes, state_key)
            
            business_rules: List[BusinessRule] = []
            safety_rules: List[SafetyRule] = []
            validation_rules: List[ValidationRule] = []
            evidence_specs: List[EvidenceSpec] = []
            transitions: List[Transition] = list(dec_transitions)
            
            for n in block_nodes:
                if n.node_type == "DIRECTIVE_BLOCK" and n.metadata.get("directive_type") == "rule":
                    r_code = sanitize_code(n.metadata.get("directive_code") or f"RULE_{len(business_rules)+len(safety_rules)+1}", prefix="RULE")
                    r_props = n.metadata.get("properties", {})
                    r_type = r_props.get("type", "SAFETY_GUARDRAIL").upper()
                    r_enforcement = r_props.get("enforcement", "HARD_STOP").upper()
                    clean_logic = n.content.strip()
                    
                    if r_type == "SAFETY_GUARDRAIL":
                        safety_rules.append(SafetyRule(
                            rule_code=r_code,
                            condition_logic=clean_logic,
                            enforcement_level=r_enforcement,
                            error_message=f"Safety Violation ({r_code}): {clean_logic}"
                        ))
                    else:
                        business_rules.append(BusinessRule(
                            rule_code=r_code,
                            rule_type=r_type if r_type in ('SAFETY_GUARDRAIL', 'INPUT_VALIDATION', 'PREREQUISITE', 'COMPLIANCE_CHECK') else 'COMPLIANCE_CHECK',
                            condition_logic=clean_logic,
                            error_message=f"Business Rule Violation ({r_code}): {clean_logic}"
                        ))
                        
                elif n.node_type == "DIRECTIVE_BLOCK" and n.metadata.get("directive_type") == "evidence":
                    e_code = sanitize_code(n.metadata.get("directive_code") or f"EVIDENCE_{len(evidence_specs)+1}", prefix="EVIDENCE")
                    e_props = n.metadata.get("properties", {})
                    e_type = e_props.get("type", "DOCUMENT_PDF").upper()
                    is_req = str(e_props.get("required", "True")).lower() == "true"
                    
                    evidence_specs.append(EvidenceSpec(
                        evidence_code=e_code,
                        evidence_type=e_type,
                        min_size_bytes=1024,
                        is_required=is_req
                    ))
                    
                elif n.node_type == "INLINE_DIRECTIVE" and n.metadata.get("directive_type") == "transition":
                    t_props = n.metadata.get("properties", {})
                    to_state = sanitize_code(t_props.get("to", "STATE_END"), prefix="STATE")
                    c_type = t_props.get("condition", "ALWAYS").upper()
                    expr = t_props.get("expression", c_type)
                    
                    transitions.append(Transition(
                        from_state_key=state_key,
                        to_state_key=to_state,
                        condition_type=c_type if c_type in ('ALWAYS', 'EXPRESSION', 'DECISION_OPTION', 'RULE_PASS', 'RULE_FAIL', 'FALLBACK') else 'ALWAYS',
                        condition_expression=expr,
                        priority=10
                    ))

            state_type = str(props.get("type", "ATOMIC_STEP")).upper()
            def parse_bool(value: Any, default: bool) -> bool:
                if value is None:
                    return default
                if isinstance(value, bool):
                    return value
                return str(value).strip().lower() in {"1", "true", "yes", "on"}

            is_init = parse_bool(props.get("is_initial"), i == 0)
            is_term = parse_bool(
                props.get("is_terminal"),
                state_type == "END" or i == len(state_blocks) - 1,
            )

            states.append(
                State(
                    state_key=state_key,
                    state_type=state_type if state_type in ('START', 'ATOMIC_STEP', 'DECISION', 'PARALLEL_GATE', 'ESCALATION', 'END') else 'ATOMIC_STEP',
                    title=state_title,
                    purpose=props.get("purpose", f"Execute operations for {state_title}"),
                    entry_condition=props.get("entry_condition"),
                    exit_condition=props.get("exit_condition"),
                    responsible_role=str(props.get("responsible_role") or props.get("role") or "Warehouse Operations Clerk"),
                    expected_duration=str(props.get("expected_duration") or props.get("duration") or "10 mins"),
                    business_objective=props.get("business_objective", state_title),
                    description=description or state_title,
                    is_initial=is_init,
                    is_terminal=is_term,
                    ordinal_index=i + 1,
                    steps=steps,
                    decisions=decisions,
                    business_rules=business_rules,
                    safety_rules=safety_rules,
                    validation_rules=validation_rules,
                    evidence_specs=evidence_specs,
                    transitions=transitions,
                )
            )

        # Filter out the default STATE_START if it has no meaningful content (i.e. it just caught top-level metadata)
        filtered_states = []
        for s in states:
            if s.state_key == "STATE_START" and not s.steps and not s.decisions and not s.business_rules and not s.safety_rules and not s.transitions:
                continue
            filtered_states.append(s)

        # Re-evaluate is_initial for the first state if we dropped STATE_START
        if filtered_states and not any(s.is_initial for s in filtered_states):
            filtered_states[0].is_initial = True

        return filtered_states
