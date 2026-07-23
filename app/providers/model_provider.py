"""Language-model, embedding, and reranking provider contracts."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol


class ChatModelProvider(Protocol):
    async def complete(self, messages: Sequence[dict[str, str]]) -> str: ...


class EmbeddingProvider(Protocol):
    @property
    def dimensions(self) -> int: ...

    async def embed(self, texts: Sequence[str]) -> list[list[float]]: ...


class RerankerProvider(Protocol):
    async def rerank(self, query: str, documents: Sequence[str]) -> list[float]: ...

