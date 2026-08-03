"""基于百炼 OpenAI-compatible 接口的异步文本重排适配器。"""

from __future__ import annotations

import math
from collections.abc import Awaitable, Callable, Mapping, Sequence
from time import perf_counter
from typing import Any, cast

from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AsyncOpenAI,
    AuthenticationError,
    PermissionDeniedError,
    RateLimitError,
)

from app.config import Settings
from app.observability.metrics import record_model_call
from app.observability.tracing import start_span
from app.providers.model_provider import RerankerProvider, RerankerProviderError
from app.rag.constants import DASHSCOPE_EMBEDDING_PROVIDER

RerankCall = Callable[..., Awaitable[object]]


class RerankerProviderFailure(RerankerProviderError):
    """供检索服务记录并回退到融合排序的安全失败。"""


class DashScopeRerankerProvider:
    """调用 qwen3-rerank，并将排序响应恢复为与输入文档相同的顺序。"""

    def __init__(
        self,
        settings: Settings,
        *,
        call: RerankCall | None = None,
    ) -> None:
        api_key = (
            settings.dashscope_api_key.get_secret_value()
            if settings.dashscope_api_key is not None
            else None
        )
        self._api_key = api_key if api_key and api_key.strip() else None
        self._model_name = settings.reranker_model
        self._client: AsyncOpenAI | None = None
        self._call = call
        if call is None and self._api_key is not None:
            self._client = AsyncOpenAI(
                api_key=self._api_key,
                base_url=settings.reranker_base_url,
                timeout=float(settings.reranker_timeout_seconds),
                max_retries=settings.reranker_max_retries,
            )
            self._call = cast(RerankCall, self._client.post)

    @property
    def provider_name(self) -> str:
        return DASHSCOPE_EMBEDDING_PROVIDER

    @property
    def model_name(self) -> str:
        return self._model_name

    async def rerank(self, query: str, documents: Sequence[str]) -> list[float]:
        normalized_query = query.strip()
        normalized_documents = [document.strip() for document in documents]
        if not normalized_query or not normalized_documents or any(
            not document for document in normalized_documents
        ):
            raise RerankerProviderFailure("reranker_input_invalid", retryable=False)

        call = self._require_call()
        started = perf_counter()
        outcome = "error"
        with start_span(
            "model.rerank",
            provider=self.provider_name,
            model=self.model_name,
        ):
            try:
                response = await call(
                    "/reranks",
                    body={
                        "model": self._model_name,
                        "query": normalized_query,
                        "documents": normalized_documents,
                        "top_n": len(normalized_documents),
                    },
                    cast_to=object,
                )
                scores = _validated_scores(
                    response,
                    expected_count=len(normalized_documents),
                )
                outcome = "success"
                return scores
            except RerankerProviderFailure:
                raise
            except Exception as exc:
                raise _provider_failure(exc) from exc
            finally:
                record_model_call(
                    provider=self.provider_name,
                    model=self.model_name,
                    mode="rerank",
                    outcome=outcome,
                    duration_seconds=perf_counter() - started,
                )

    async def close(self) -> None:
        """释放底层异步 HTTP 连接池。"""

        if self._client is not None:
            await self._client.close()

    def _require_call(self) -> RerankCall:
        if self._api_key is None and self._call is None:
            raise RerankerProviderFailure("reranker_configuration_missing", retryable=False)
        if self._call is None:
            raise RerankerProviderFailure("reranker_configuration_missing", retryable=False)
        return self._call


def _validated_scores(response: object, *, expected_count: int) -> list[float]:
    results = _value(response, "results")
    if not isinstance(results, Sequence) or isinstance(results, (str, bytes)):
        raise RerankerProviderFailure("reranker_response_invalid", retryable=True)
    ordered: list[float | None] = [None] * expected_count
    for result in results:
        try:
            index = int(_value(result, "index"))
            score = float(_value(result, "relevance_score"))
        except (TypeError, ValueError) as exc:
            raise RerankerProviderFailure(
                "reranker_response_invalid",
                retryable=True,
            ) from exc
        if (
            index < 0
            or index >= expected_count
            or ordered[index] is not None
            or not math.isfinite(score)
            or not 0.0 <= score <= 1.0
        ):
            raise RerankerProviderFailure("reranker_response_invalid", retryable=True)
        ordered[index] = score
    if any(score is None for score in ordered):
        raise RerankerProviderFailure("reranker_response_invalid", retryable=True)
    return cast(list[float], ordered)


def _provider_failure(exc: Exception) -> RerankerProviderFailure:
    if isinstance(exc, APITimeoutError):
        return RerankerProviderFailure("reranker_provider_timeout", retryable=True)
    if isinstance(exc, (AuthenticationError, PermissionDeniedError)):
        return RerankerProviderFailure(
            "reranker_provider_authentication_failed",
            retryable=False,
        )
    if isinstance(exc, RateLimitError):
        return RerankerProviderFailure("reranker_provider_rate_limited", retryable=True)
    if isinstance(exc, APIConnectionError):
        return RerankerProviderFailure("reranker_provider_unavailable", retryable=True)
    status_code = getattr(exc, "status_code", None)
    if isinstance(exc, APIStatusError) or isinstance(status_code, int):
        retryable = status_code in {408, 409, 429} or (
            isinstance(status_code, int) and status_code >= 500
        )
        return RerankerProviderFailure(
            "reranker_provider_rejected_request",
            retryable=retryable,
        )
    return RerankerProviderFailure("reranker_provider_unavailable", retryable=True)


def _value(value: object, key: str, *, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        return value.get(key, default)
    return getattr(value, key, default)


def as_reranker_provider(provider: DashScopeRerankerProvider) -> RerankerProvider:
    """让严格类型检查显式验证 Provider 协议实现。"""

    return provider
