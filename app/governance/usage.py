"""跨模型调用累计一次业务运行实际 Token 用量。"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass


@dataclass(slots=True)
class ModelTokenCounter:
    total_tokens: int = 0


_COUNTER: ContextVar[ModelTokenCounter | None] = ContextVar(
    "aurum_model_token_counter", default=None
)


@contextmanager
def collect_model_tokens() -> Iterator[ModelTokenCounter]:
    counter = ModelTokenCounter()
    token = _COUNTER.set(counter)
    try:
        yield counter
    finally:
        _COUNTER.reset(token)


def add_model_tokens(total_tokens: int) -> None:
    counter = _COUNTER.get()
    if counter is not None and total_tokens > 0:
        counter.total_tokens += total_tokens
