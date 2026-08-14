"""OWD Markdown Parser Module (v1.1 Knowledge Compiler).

Delegates parsing to the modular ASTBuilder pipeline while maintaining 100% backward
compatibility for existing callers.
"""

import logging
from app.compiler.models import UnifiedAST
from app.compiler.parsers.ast_builder import ASTBuilder
from app.compiler.exceptions import OWDParsingException

logger = logging.getLogger("compiler.parser")


class OWDParser:
    """Parses raw OWD Markdown into a structured UnifiedAST / OWDDocument object graph."""

    @staticmethod
    def parse(
        markdown_text: str,
        workflow_code: str = "",
        title: str = "",
        department_id: str = "",
        category: str = "OPERATIONAL_SOP",
        default_version: int = 1,
    ) -> UnifiedAST:
        """Reads raw OWD markdown text and builds an unvalidated UnifiedAST object graph."""
        if not markdown_text or not isinstance(markdown_text, str) or not markdown_text.strip():
            raise OWDParsingException("OWD markdown source content is empty or invalid.")

        try:
            return ASTBuilder.build_ast(
                markdown_text=markdown_text,
                workflow_code=workflow_code,
                title=title,
                department_id=department_id,
                category=category,
                default_version=default_version,
            )
        except Exception as exc:
            logger.error(f"[OWD PARSER ERROR] Failed to parse OWD document: {exc}")
            raise OWDParsingException(f"Parsing failed: {str(exc)}") from exc
