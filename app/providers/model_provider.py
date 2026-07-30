"""Language-model, embedding, and reranking provider contracts."""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from typing import Protocol

from app.chat.types import ChatPromptRole


class ChatModelProviderError(RuntimeError):
    """聊天模型适配器对编排层暴露的安全、可分类失败。"""

    def __init__(self, code: str, *, retryable: bool) -> None:
        super().__init__(code)
        self.code = code
        self.retryable = retryable


class RerankerProviderError(RuntimeError):
    """检索服务可安全降级处理的重排 Provider 失败。"""

    def __init__(self, code: str, *, retryable: bool) -> None:
        super().__init__(code)
        self.code = code
        self.retryable = retryable


@dataclass(frozen=True, slots=True)
class ChatMessage:
    """一条与具体模型 SDK 无关的提示消息。"""

    role: ChatPromptRole
    content: str


@dataclass(frozen=True, slots=True)
class ChatTokenUsage:
    """一次模型调用可持久化的 Token 用量。"""

    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


@dataclass(frozen=True, slots=True)
class ChatCompletionResult:
    """非流式文本生成的规范化结果。"""

    content: str
    model: str
    finish_reason: str | None
    request_id: str | None
    usage: ChatTokenUsage | None


@dataclass(frozen=True, slots=True)
class ChatStreamChunk:
    """流式文本增量；末尾的用量块可以不包含文本。"""

    delta: str
    model: str
    finish_reason: str | None
    request_id: str | None
    usage: ChatTokenUsage | None


class ChatModelProvider(Protocol):
    """可替换的纯文本聊天模型能力。"""

    @property
    def provider_name(self) -> str: ...

    @property
    def model_name(self) -> str: ...

    async def complete(self, messages: Sequence[ChatMessage]) -> ChatCompletionResult: ...

    def stream(self, messages: Sequence[ChatMessage]) -> AsyncIterator[ChatStreamChunk]: ...


class EmbeddingProvider(Protocol):
    """Provider-neutral batch embedding contract for a single index space."""

    @property
    def provider_name(self) -> str: ...

    @property
    def model_name(self) -> str: ...

    @property
    def dimensions(self) -> int: ...

    async def embed(self, texts: Sequence[str]) -> list[list[float]]: ...


class QueryEmbeddingProvider(Protocol):
    """Provider-neutral query embedding contract for retrieval."""

    @property
    def provider_name(self) -> str: ...

    @property
    def model_name(self) -> str: ...

    @property
    def dimensions(self) -> int: ...

    async def embed_query(self, query: str) -> list[float]: ...


class RerankerProvider(Protocol):
    @property
    def provider_name(self) -> str: ...

    @property
    def model_name(self) -> str: ...

    async def rerank(self, query: str, documents: Sequence[str]) -> list[float]: ...
