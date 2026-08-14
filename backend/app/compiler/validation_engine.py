"""Validation Engine & AST Enrichment Module.

Provides AST enrichment and delegates canonical validation to OWDValidator.
Separates AST state/step index enrichment from validation logic.
"""

import logging
from typing import Set
from app.compiler.models import UnifiedAST

logger = logging.getLogger("compiler.validation_engine")


class ValidationEngine:
    """Provides enrichment for compiled UnifiedAST objects and delegates validation to canonical OWDValidator."""

    @staticmethod
    def enrich_ast(ast: UnifiedAST) -> UnifiedAST:
        """Enriches step ordinal indices and default initial/terminal state flags."""
        global_index = 1
        seen_codes: Set[str] = set()

        for state in ast.workflow.states:
            for step in state.steps:
                step.ordinal_index = global_index
                global_index += 1

                if step.step_code in seen_codes:
                    logger.warning(f"Duplicate step code detected: {step.step_code}")
                seen_codes.add(step.step_code)

        states = ast.workflow.states
        if states:
            if not any(s.is_initial for s in states):
                states[0].is_initial = True
            if not any(s.is_terminal for s in states):
                states[-1].is_terminal = True

        return ast

    @staticmethod
    def validate_and_enrich(ast: UnifiedAST) -> UnifiedAST:
        """Enriches step ordinal indices and verifies canonical graph validation via OWDValidator."""
        ast = ValidationEngine.enrich_ast(ast)
        from app.compiler.validator import OWDValidator

        val_report = OWDValidator.validate(ast)
        if not val_report.is_valid:
            logger.warning(f"[VALIDATION ENGINE] Canonical validation flagged {len(val_report.errors)} issues.")

        return ast
