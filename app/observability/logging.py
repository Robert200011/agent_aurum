"""字段白名单、上下文注入和敏感数据脱敏的结构化日志。"""

from __future__ import annotations

import json
import logging
import re
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Final
from uuid import UUID

from app.observability.context import current_context

REDACTED: Final = "[REDACTED]"
_MAX_VALUE_LENGTH: Final = 512
_ALLOWED_EXTRA_FIELDS: Final = frozenset(
    {
        "event",
        "error_code",
        "operation",
        "outcome",
        "method",
        "route",
        "status_code",
        "duration_ms",
        "provider",
        "model",
        "tool",
        "task",
        "retryable",
        "result_count",
        "job_id",
        "document_id",
        "owner_user_id",
        "knowledge_base_id",
        "conversation_id",
        "agent_run_id",
        "run_id",
    }
)
_ASSIGNMENT_PATTERN = re.compile(
    r"(?i)(authorization|cookie|set-cookie|api[_-]?key|secret|password|access[_-]?token|"
    r"refresh[_-]?token|prompt|question|document[_-]?(?:content|body)|content|description)"
    r"(\s*[=:]\s*)(?:\"[^\"]*\"|'[^']*'|[^,;\s]+)"
)
_BEARER_PATTERN = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+")
_JWT_PATTERN = re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b")
_DATABASE_URL_PATTERN = re.compile(
    r"(?i)\b(postgresql(?:\+[a-z0-9]+)?|mysql(?:\+[a-z0-9]+)?|redis)://"
    r"([^\s:/@]+):([^\s@]+)@"
)
_CARD_PATTERN = re.compile(r"(?<!\d)(?:\d[ -]?){12,18}\d(?!\d)")


def redact_text(value: object) -> str:
    """清除常见凭据、连接串、用户正文标签和银行卡号。"""

    text = str(value)
    text = _DATABASE_URL_PATTERN.sub(r"\1://\2:[REDACTED]@", text)
    text = _BEARER_PATTERN.sub(f"Bearer {REDACTED}", text)
    text = _JWT_PATTERN.sub(REDACTED, text)
    text = _ASSIGNMENT_PATTERN.sub(
        lambda match: f"{match.group(1)}{match.group(2)}{REDACTED}",
        text,
    )
    text = _CARD_PATTERN.sub(REDACTED, text)
    if len(text) > _MAX_VALUE_LENGTH:
        return f"{text[:_MAX_VALUE_LENGTH]}...[TRUNCATED]"
    return text


def _safe_scalar(value: object) -> str | int | float | bool | None:
    if value is None or isinstance(value, (int, float, bool)):
        return value
    if isinstance(value, (UUID, Enum)):
        value = str(value.value if isinstance(value, Enum) else value)
    return redact_text(value)


class SensitiveDataFilter(logging.Filter):
    """在格式化前构造安全消息，参数永不直接写入日志。"""

    def filter(self, record: logging.LogRecord) -> bool:
        message = redact_text(record.msg)
        if record.args:
            message = f"{message} [arguments redacted]"
        record.safe_message = message
        if record.exc_info and record.exc_info[1] is not None:
            record.safe_exception_type = type(record.exc_info[1]).__name__
            record.safe_exception_message = redact_text(record.exc_info[1])
        return True


class JsonFormatter(logging.Formatter):
    """每行输出一个仅含白名单字段和安全异常摘要的 JSON 对象。"""

    def __init__(self, service_name: str = "aurum-agent") -> None:
        super().__init__()
        self._service_name = redact_text(service_name)[:128]

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "service": self._service_name,
            "message": getattr(record, "safe_message", redact_text(record.msg)),
        }
        payload.update(current_context())
        for field in _ALLOWED_EXTRA_FIELDS:
            if field in payload:
                continue
            if hasattr(record, field):
                payload[field] = _safe_scalar(getattr(record, field))
        exception_type = getattr(record, "safe_exception_type", None)
        if exception_type:
            payload["exception_type"] = exception_type
            payload["exception_message"] = getattr(
                record,
                "safe_exception_message",
                "exception details unavailable",
            )
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def configure_logging(level: str, service_name: str = "aurum-agent") -> None:
    """配置容器标准输出；重复调用不会累积处理器。"""

    handler = logging.StreamHandler()
    handler.addFilter(SensitiveDataFilter())
    handler.setFormatter(JsonFormatter(service_name))
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level.upper())
