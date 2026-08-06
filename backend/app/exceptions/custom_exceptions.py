"""Custom exception classes for WorkMate AI backend."""

class WorkMateException(Exception):
    """Base exception for WorkMate AI platform."""
    def __init__(self, message: str = "An internal error occurred.", error_code: str = "WORKMATE_ERROR", details: dict = None):
        self.message = message
        self.error_code = error_code
        self.details = details or {}
        super().__init__(self.message)

class TokenExpiredError(WorkMateException):
    """Raised when a JWT access or refresh token has expired."""
    def __init__(self, message: str = "JWT token has expired.", details: dict = None):
        super().__init__(message=message, error_code="TOKEN_EXPIRED", details=details)

class TokenInvalidError(WorkMateException):
    """Raised when a JWT token signature or payload claims are invalid."""
    def __init__(self, message: str = "Invalid JWT token.", details: dict = None):
        super().__init__(message=message, error_code="TOKEN_INVALID", details=details)

class AuthenticationException(WorkMateException):
    """Raised on general authentication failures."""
    def __init__(self, message: str = "Authentication failed.", details: dict = None):
        super().__init__(message=message, error_code="AUTHENTICATION_FAILED", details=details)

class DatabaseException(WorkMateException):
    """Raised on database operation failures."""
    def __init__(self, message: str = "Database operation failed.", details: dict = None):
        super().__init__(message=message, error_code="DATABASE_ERROR", details=details)

class NotFoundException(WorkMateException):
    """Raised when a requested resource is not found."""
    def __init__(self, message: str = "Resource not found.", details: dict = None):
        super().__init__(message=message, error_code="NOT_FOUND", details=details)

class ExternalServiceException(WorkMateException):
    """Raised on external API/service failures."""
    def __init__(self, message: str = "External service call failed.", details: dict = None):
        super().__init__(message=message, error_code="EXTERNAL_SERVICE_ERROR", details=details)
