"""Compiler Exception Hierarchy.

Provides domain-specific exceptions for OWD Parsing, Validation, Compilation, and Loading stages.
"""

from typing import Optional, List, Dict, Any


class CompilerBaseException(Exception):
    """Base exception for all OWD Compiler subsystem failures."""
    def __init__(self, message: str = "An OWD compiler error occurred.", details: Optional[Dict[str, Any]] = None):
        self.message = message
        self.details = details or {}
        super().__init__(self.message)


class OWDParsingException(CompilerBaseException):
    """Raised when OWD Markdown parsing encounters syntax or format errors."""
    def __init__(self, message: str, line_number: Optional[int] = None):
        super().__init__(message, details={"line_number": line_number})
        self.line_number = line_number


class OWDValidationException(CompilerBaseException):
    """Raised when an OWD Document fails graph or business rule validation checks."""
    def __init__(self, message: str, validation_errors: Optional[List[str]] = None):
        errors = validation_errors or []
        super().__init__(message, details={"validation_errors": errors})
        self.validation_errors = errors


class OWDCompilationException(CompilerBaseException):
    """Raised when transformation from OWD AST to CompiledWorkflow fails."""
    def __init__(self, message: str):
        super().__init__(message)


class OWDLoaderException(CompilerBaseException):
    """Raised when Snowflake database loading or MERGE fails."""
    def __init__(self, message: str, table_name: Optional[str] = None):
        super().__init__(message, details={"table_name": table_name})
        self.table_name = table_name
