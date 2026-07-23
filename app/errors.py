"""Domain errors translated into stable API error responses."""

from __future__ import annotations


class ApplicationError(Exception):
    """Base error with an API-safe code and message."""

    status_code = 400
    code = "application_error"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class AuthenticationError(ApplicationError):
    status_code = 401
    code = "authentication_failed"


class AuthorizationError(ApplicationError):
    status_code = 403
    code = "permission_denied"


class ConflictError(ApplicationError):
    status_code = 409
    code = "resource_conflict"


class RateLimitError(ApplicationError):
    status_code = 429
    code = "rate_limit_exceeded"


class ServiceUnavailableError(ApplicationError):
    status_code = 503
    code = "service_unavailable"
