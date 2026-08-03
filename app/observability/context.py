"""使用 ``contextvars`` 传播不包含业务正文的观测关联字段。"""

from __future__ import annotations

import hashlib
import hmac
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar, Token
from typing import Final
from uuid import UUID

_FIELD_NAMES: Final = (
    "request_id",
    "trace_id",
    "conversation_id",
    "agent_run_id",
    "user_hash",
)
_CONTEXT: dict[str, ContextVar[str | None]] = {
    name: ContextVar(f"aurum_{name}", default=None) for name in _FIELD_NAMES
}


def current_context() -> dict[str, str]:
    """返回当前执行上下文中已经设置的安全关联字段。"""

    return {
        name: value
        for name, variable in _CONTEXT.items()
        if (value := variable.get()) is not None
    }


def set_context(**values: str | UUID | None) -> tuple[tuple[str, Token[str | None]], ...]:
    """设置给定字段，并返回可用于精确恢复旧上下文的 token。"""

    unknown = set(values).difference(_CONTEXT)
    if unknown:
        raise ValueError(f"unsupported observability context fields: {sorted(unknown)}")
    tokens: list[tuple[str, Token[str | None]]] = []
    for name, value in values.items():
        normalized = str(value)[:128] if value is not None else None
        tokens.append((name, _CONTEXT[name].set(normalized)))
    return tuple(tokens)


def reset_context(tokens: tuple[tuple[str, Token[str | None]], ...]) -> None:
    """按逆序恢复上下文，防止复用协程时发生关联字段串线。"""

    for name, token in reversed(tokens):
        _CONTEXT[name].reset(token)


@contextmanager
def bound_context(**values: str | UUID | None) -> Iterator[None]:
    """在一个同步或异步调用作用域内临时绑定关联字段。"""

    tokens = set_context(**values)
    try:
        yield
    finally:
        reset_context(tokens)


def user_identifier_hash(user_id: UUID | str, secret: bytes) -> str:
    """生成环境相关、不可逆且稳定的用户日志标识。"""

    digest = hmac.new(secret, str(user_id).encode("utf-8"), hashlib.sha256).hexdigest()
    return digest[:24]
