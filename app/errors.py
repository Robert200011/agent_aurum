"""转换为稳定 API 错误响应的领域错误。"""

from __future__ import annotations


class ApplicationError(Exception):
    """包含 API 安全错误码与消息的基础错误。"""

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


class NotFoundError(ApplicationError):
    status_code = 404
    code = "resource_not_found"


class ConflictError(ApplicationError):
    status_code = 409
    code = "resource_conflict"


class BusinessRuleError(ApplicationError):
    status_code = 422
    code = "business_rule_violation"


class RateLimitError(ApplicationError):
    status_code = 429
    code = "rate_limit_exceeded"

    def __init__(self, message: str, *, retry_after_seconds: int) -> None:
        super().__init__(message)
        self.retry_after_seconds = max(1, retry_after_seconds)


class ServiceUnavailableError(ApplicationError):
    status_code = 503
    code = "service_unavailable"
