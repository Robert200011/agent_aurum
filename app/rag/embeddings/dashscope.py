"""Validated asynchronous adapter for DashScope text-embedding-v4."""

from __future__ import annotations

import asyncio
import math
from collections.abc import Callable, Mapping, Sequence
from typing import Any, Literal, cast

from dashscope import TextEmbedding  # type: ignore[import-untyped, unused-ignore]

from app.config import Settings
from app.providers.model_provider import EmbeddingProvider
from app.rag.constants import DASHSCOPE_EMBEDDING_PROVIDER


class EmbeddingProviderFailure(RuntimeError):
    """Safe provider failure metadata consumed by the ingestion state machine."""

    def __init__(self, code: str, *, retryable: bool) -> None:
        super().__init__(code)
        self.code = code
        self.retryable = retryable


class DashScopeEmbeddingProvider:
    """Batch text embeddings with strict order, shape, and finite-value checks."""

    def __init__(
        self,
        settings: Settings,
        *,
        call: Callable[..., object] | None = None,
    ) -> None:
        self._api_key = (
            settings.dashscope_api_key.get_secret_value()
            if settings.dashscope_api_key is not None
            else None
        )
        self._model_name = settings.embedding_model
        self._dimensions = settings.embedding_dimensions
        self._batch_size = settings.embedding_batch_size
        self._timeout_seconds = settings.embedding_request_timeout_seconds
        self._call = call or cast(Callable[..., object], TextEmbedding.call)

    @property
    def provider_name(self) -> str:
        return DASHSCOPE_EMBEDDING_PROVIDER

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def dimensions(self) -> int:
        return self._dimensions

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return await self._embed(texts, text_type="document")

    async def embed_query(self, query: str) -> list[float]:
        vectors = await self._embed([query], text_type="query")
        return vectors[0]

    async def _embed(
        self,
        texts: Sequence[str],
        *,
        text_type: Literal["document", "query"],
    ) -> list[list[float]]:
        if not texts:
            return []
        if self._api_key is None:
            raise EmbeddingProviderFailure(
                "embedding_configuration_missing",
                retryable=False,
            )
        vectors: list[list[float]] = []
        for start in range(0, len(texts), self._batch_size):
            batch = list(texts[start : start + self._batch_size])
            if any(not text.strip() for text in batch):
                raise EmbeddingProviderFailure("embedding_input_empty", retryable=False)
            try:
                response = await asyncio.to_thread(
                    self._call,
                    model=self._model_name,
                    input=batch,
                    api_key=self._api_key,
                    text_type=text_type,
                    dimension=self._dimensions,
                    output_type="dense",
                    timeout=self._timeout_seconds,
                )
            except EmbeddingProviderFailure:
                raise
            except Exception as exc:
                raise EmbeddingProviderFailure(
                    "embedding_provider_unavailable",
                    retryable=True,
                ) from exc
            vectors.extend(self._validated_vectors(response, expected_count=len(batch)))
        return vectors

    def _validated_vectors(self, response: object, *, expected_count: int) -> list[list[float]]:
        status_code = int(_response_value(response, "status_code", default=0))
        if status_code != 200:
            raise EmbeddingProviderFailure(
                "embedding_provider_rejected_request",
                retryable=status_code == 429 or status_code >= 500 or status_code == 0,
            )
        output = _response_value(response, "output")
        if not isinstance(output, Mapping):
            raise EmbeddingProviderFailure("embedding_response_invalid", retryable=True)
        items = output.get("embeddings")
        if not isinstance(items, Sequence) or isinstance(items, (str, bytes)):
            raise EmbeddingProviderFailure("embedding_response_invalid", retryable=True)

        ordered: list[list[float] | None] = [None] * expected_count
        for raw_item in items:
            if not isinstance(raw_item, Mapping):
                raise EmbeddingProviderFailure("embedding_response_invalid", retryable=True)
            try:
                index = int(raw_item["text_index"])
                raw_vector = raw_item["embedding"]
            except (KeyError, TypeError, ValueError) as exc:
                raise EmbeddingProviderFailure(
                    "embedding_response_invalid",
                    retryable=True,
                ) from exc
            if (
                index < 0
                or index >= expected_count
                or ordered[index] is not None
                or not isinstance(raw_vector, Sequence)
                or isinstance(raw_vector, (str, bytes))
                or len(raw_vector) != self._dimensions
            ):
                raise EmbeddingProviderFailure("embedding_response_invalid", retryable=True)
            try:
                vector = [float(value) for value in raw_vector]
            except (TypeError, ValueError) as exc:
                raise EmbeddingProviderFailure(
                    "embedding_response_invalid",
                    retryable=True,
                ) from exc
            if not all(math.isfinite(value) for value in vector):
                raise EmbeddingProviderFailure("embedding_response_invalid", retryable=True)
            ordered[index] = vector
        if any(vector is None for vector in ordered):
            raise EmbeddingProviderFailure("embedding_response_invalid", retryable=True)
        return cast(list[list[float]], ordered)


def _response_value(response: object, key: str, *, default: Any = None) -> Any:
    if isinstance(response, Mapping):
        return response.get(key, default)
    return getattr(response, key, default)


def as_embedding_provider(provider: DashScopeEmbeddingProvider) -> EmbeddingProvider:
    """Keep protocol conformance visible to strict type checking."""

    return provider
