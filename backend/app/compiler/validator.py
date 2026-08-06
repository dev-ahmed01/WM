"""OWD AST Validator Module (v1.1 Knowledge Compiler).

Validates parsed UnifiedAST / OWDDocument AST graphs for structural integrity,
graph reachability, broken transitions, duplicate keys, missing mandatory components,
invalid retry policies, and permission definitions.
Does NOT execute SQL or access Snowflake.
"""

import logging
from typing import List, Set, Dict, Any

from app.compiler.models import OWDDocument, ValidationReport, UnifiedAST
from app.compiler.utils import find_unreachable_states
from app.compiler.exceptions import OWDValidationException

logger = logging.getLogger("compiler.validator")


class OWDValidator:
    """Validates structural correctness and graph completeness of parsed UnifiedAST / OWDDocument objects."""

    @staticmethod
    def validate(owd_document: UnifiedAST, raise_on_error: bool = False) -> ValidationReport:
        """Inspects UnifiedAST and returns a detailed ValidationReport containing errors and warnings."""
        if not owd_document or not owd_document.workflow:
            report = ValidationReport(
                is_valid=False,
                errors=["Invalid OWD document: Document or workflow entity is missing."],
            )
            if raise_on_error:
                raise OWDValidationException("OWD Validation Failed", validation_errors=report.errors)
            return report

        errors: List[str] = []
        warnings: List[str] = []

        wf = owd_document.workflow
        states = wf.states

        # 1. Verify workflow code & states existence
        if not wf.workflow_code or not wf.workflow_code.strip():
            errors.append("Missing required workflow code.")

        if not states:
            errors.append(f"Workflow '{wf.workflow_code}' has no state definitions.")
            report = ValidationReport(is_valid=False, errors=errors)
            if raise_on_error:
                raise OWDValidationException("OWD Validation Failed", validation_errors=report.errors)
            return report

        # 2. Check metadata completeness
        if owd_document.spec_version == "1.1":
            if not owd_document.metadata or not owd_document.metadata.sop_id:
                warnings.append(f"OWD v1.1 document '{wf.workflow_code}' is missing explicit Document Metadata block.")

        # 3. Check for initial state
        initial_states = [s for s in states if s.is_initial]
        if len(initial_states) == 0:
            warnings.append(f"No explicit initial state marked for '{wf.workflow_code}'. Defaulting first state '{states[0].state_key}' as entry node.")
            states[0].is_initial = True
        elif len(initial_states) > 1:
            errors.append(f"Multiple initial states defined ({[s.state_key for s in initial_states]}). Exactly one entry state must be marked is_initial=true.")

        # 4. Check for duplicate state keys
        seen_state_keys: Set[str] = set()
        duplicate_state_keys: Set[str] = set()

        for s in states:
            if s.state_key in seen_state_keys:
                duplicate_state_keys.add(s.state_key)
            seen_state_keys.add(s.state_key)

        if duplicate_state_keys:
            errors.append(f"Duplicate state keys detected: {list(duplicate_state_keys)}.")

        # 5. Check for step, decision, and rule code duplicates & invalid fields
        seen_step_codes: Set[str] = set()
        seen_rule_codes: Set[str] = set()
        seen_decision_codes: Set[str] = set()

        steps_count = 0
        decisions_count = 0
        business_rules_count = 0
        safety_rules_count = 0
        validation_rules_count = 0

        valid_retry_policies = {'MAX_RETRIES_1', 'MAX_RETRIES_3', 'MAX_RETRIES_5', 'NO_RETRY', 'SUPERVISOR_OVERRIDE'}

        for s in states:
            steps_count += len(s.steps)
            decisions_count += len(s.decisions)
            business_rules_count += len(s.business_rules)
            safety_rules_count += len(s.safety_rules)
            validation_rules_count += len(s.validation_rules)

            for step in s.steps:
                if step.step_code in seen_step_codes:
                    warnings.append(f"Duplicate step code '{step.step_code}' in state '{s.state_key}'.")
                seen_step_codes.add(step.step_code)

                # Check retry policy validity
                if step.retry_policy and step.retry_policy.upper() not in valid_retry_policies:
                    warnings.append(f"Non-standard retry policy '{step.retry_policy}' for step '{step.step_code}'. Defaulting to MAX_RETRIES_3.")

            for dec in s.decisions:
                if dec.decision_code in seen_decision_codes:
                    warnings.append(f"Duplicate decision code '{dec.decision_code}' in state '{s.state_key}'.")
                seen_decision_codes.add(dec.decision_code)

            for rule in s.safety_rules + s.business_rules:
                r_code = getattr(rule, "rule_code", "")
                if r_code and r_code in seen_rule_codes:
                    warnings.append(f"Duplicate rule code '{r_code}' in state '{s.state_key}'.")
                if r_code:
                    seen_rule_codes.add(r_code)

        # 6. Check graph transitions and broken target references
        all_transitions: List[Dict[str, str]] = []
        for s in states:
            for t in s.transitions:
                all_transitions.append({
                    "from_state_key": t.from_state_key,
                    "to_state_key": t.to_state_key,
                })

                # Circular self-transition warning check
                if t.from_state_key == t.to_state_key and t.condition_type == "ALWAYS":
                    errors.append(f"Circular self-transition detected on state '{s.state_key}'. Unconditional self-loop will cause infinite loop.")

                if t.to_state_key not in seen_state_keys:
                    errors.append(f"State '{s.state_key}' has broken transition target '{t.to_state_key}' which does not exist in workflow.")

            # Check decision option target state references
            for d in s.decisions:
                for opt in d.options:
                    if opt.target_state_key not in seen_state_keys:
                        errors.append(f"Decision '{d.decision_code}' option '{opt.option_code}' points to non-existent target state '{opt.target_state_key}'.")

        # 7. Check user context / permissions validity
        if owd_document.user_context:
            valid_roles = {'EMPLOYEE', 'SUPERVISOR', 'ADMIN', 'OPERATOR', 'TECHNICIAN', 'MANAGER'}
            for role in owd_document.user_context.roles:
                if role.upper() not in valid_roles:
                    warnings.append(f"Non-standard role identifier '{role}' in User Context.")

        # 8. Graph reachability analysis
        initial_key = states[0].state_key
        for s in states:
            if s.is_initial:
                initial_key = s.state_key
                break

        unreachable = find_unreachable_states(initial_key, seen_state_keys, all_transitions)
        if unreachable:
            warnings.append(f"Unreachable graph states detected: {unreachable}. Ensure transition edges connect to entry state '{initial_key}'.")

        # 9. Check for terminal exit node
        terminal_states = [s for s in states if s.is_terminal or s.state_type == "END"]
        if not terminal_states:
            warnings.append(f"No explicit terminal exit state (is_terminal=true) defined for workflow '{wf.workflow_code}'.")

        is_valid = len(errors) == 0

        report = ValidationReport(
            is_valid=is_valid,
            errors=errors,
            warnings=warnings,
            states_count=len(states),
            steps_count=steps_count,
            decisions_count=decisions_count,
            business_rules_count=business_rules_count,
            safety_rules_count=safety_rules_count,
            validation_rules_count=validation_rules_count,
        )

        if not is_valid:
            logger.warning(f"[VALIDATOR FAILED] OWD '{wf.workflow_code}' validation failed with {len(errors)} errors.")
            if raise_on_error:
                raise OWDValidationException(
                    f"OWD Validation failed for '{wf.workflow_code}' with {len(errors)} errors.",
                    validation_errors=errors,
                )
        else:
            logger.info(f"[VALIDATOR SUCCESS] OWD '{wf.workflow_code}' validated successfully ({len(warnings)} warnings).")

        return report
