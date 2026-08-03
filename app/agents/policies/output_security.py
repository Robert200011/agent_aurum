"""模型最终文本的确定性敏感信息与越权操作兜底校验。"""

from __future__ import annotations

import re

_UUID_PATTERN = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-"
    r"[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}\b"
)
_JWT_PATTERN = re.compile(
    r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"
)
_BEARER_PATTERN = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{12,}")
_SECRET_ASSIGNMENT_PATTERN = re.compile(
    r"(?i)\b(?:api[_ -]?key|password|secret|authorization|cookie)\s*[:=]"
)
_PROVIDER_KEY_PATTERN = re.compile(r"\bsk-[A-Za-z0-9_-]{12,}\b")

_SYSTEM_DISCLOSURE_MARKERS = (
    "你是 Aurum 的个人财务与知识库问答助手",
    "系统提示词如下",
    "内部提示词如下",
    "developer message",
    "system_prompt",
)
_WRITE_OPERATION_MARKERS = (
    "create_transaction",
    "update_transaction",
    "delete_transaction",
    "delete_transactions",
    "create_budget",
    "update_budget",
    "delete_budget",
    "create_account",
    "update_account",
    "delete_account",
    "execute_trade",
)


class OutputSecurityValidationError(RuntimeError):
    """最终回答包含不可向用户暴露或声称执行的安全敏感内容。"""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def validate_safe_model_output(answer: str) -> None:
    """拒绝身份标识、凭据形态、系统提示词回显和未授权写操作。"""

    normalized = answer.strip()
    if not normalized:
        raise OutputSecurityValidationError("model_output_empty")
    if _UUID_PATTERN.search(normalized):
        raise OutputSecurityValidationError("model_output_internal_identifier")
    if any(
        pattern.search(normalized)
        for pattern in (
            _JWT_PATTERN,
            _BEARER_PATTERN,
            _SECRET_ASSIGNMENT_PATTERN,
            _PROVIDER_KEY_PATTERN,
        )
    ):
        raise OutputSecurityValidationError("model_output_secret_like_value")
    folded = normalized.casefold()
    if any(marker.casefold() in folded for marker in _SYSTEM_DISCLOSURE_MARKERS):
        raise OutputSecurityValidationError("model_output_system_prompt_disclosure")
    if any(marker in folded for marker in _WRITE_OPERATION_MARKERS):
        raise OutputSecurityValidationError("model_output_write_operation")
