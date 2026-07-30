"""基于 OpenAI-compatible 接口的异步通义千问聊天适配器。"""

from __future__ import annotations

import inspect
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping, Sequence
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

from app.chat.constants import DASHSCOPE_CHAT_PROVIDER
from app.chat.types import ChatPromptRole
from app.config import Settings
from app.providers.model_provider import (
    ChatCompletionResult,
    ChatMessage,
    ChatModelProvider,
    ChatModelProviderError,
    ChatStreamChunk,
    ChatTokenUsage,
)

ChatCreateCall = Callable[..., Awaitable[object]]


class ChatModelProviderFailure(ChatModelProviderError):
    """供问答编排转换为安全 API 错误的模型调用失败。"""


class DashScopeChatModelProvider:
    """严格校验输入与响应的 DashScope OpenAI-compatible 适配器。"""

    def __init__(
        self,
        settings: Settings,
        *,
        create: ChatCreateCall | None = None,
    ) -> None:
        api_key = (
            settings.dashscope_api_key.get_secret_value()
            if settings.dashscope_api_key is not None
            else None
        )
        self._api_key = api_key if api_key and api_key.strip() else None
        self._model_name = settings.chat_model
        self._temperature = settings.chat_model_temperature
        self._max_tokens = settings.chat_model_max_tokens
        self._client: AsyncOpenAI | None = None
        self._create = create
        if create is None and self._api_key is not None:
            self._client = AsyncOpenAI(
                api_key=self._api_key,
                base_url=settings.chat_model_base_url,
                timeout=float(settings.chat_model_timeout_seconds),
                max_retries=settings.chat_model_max_retries,
            )
            self._create = cast(ChatCreateCall, self._client.chat.completions.create)

    @property
    def provider_name(self) -> str:
        return DASHSCOPE_CHAT_PROVIDER

    @property
    def model_name(self) -> str:
        return self._model_name

    async def complete(self, messages: Sequence[ChatMessage]) -> ChatCompletionResult:
        payload = _validated_messages(messages)
        create = self._require_create()
        try:
            response = await create(
                model=self._model_name,
                messages=payload,
                temperature=self._temperature,
                max_tokens=self._max_tokens,
                n=1,
                stream=False,
            )
        except ChatModelProviderFailure:
            raise
        except Exception as exc:
            raise _provider_failure(exc) from exc
        return self._parse_completion(response)

    async def stream(self, messages: Sequence[ChatMessage]) -> AsyncIterator[ChatStreamChunk]:
        payload = _validated_messages(messages)
        create = self._require_create()
        try:
            response = await create(
                model=self._model_name,
                messages=payload,
                temperature=self._temperature,
                max_tokens=self._max_tokens,
                n=1,
                stream=True,
                stream_options={"include_usage": True},
            )
            stream = _as_async_iterator(response)
            received_text = False
            try:
                async for raw_chunk in stream:
                    chunk = self._parse_stream_chunk(raw_chunk)
                    if chunk is None:
                        continue
                    received_text = received_text or bool(chunk.delta)
                    yield chunk
            finally:
                await _close_stream(response)
            if not received_text:
                raise ChatModelProviderFailure("chat_response_invalid", retryable=True)
        except ChatModelProviderFailure:
            raise
        except Exception as exc:
            raise _provider_failure(exc) from exc

    async def close(self) -> None:
        """释放底层异步 HTTP 连接池。"""

        if self._client is not None:
            await self._client.close()

    def _require_create(self) -> ChatCreateCall:
        if self._api_key is None and self._create is None:
            raise ChatModelProviderFailure("chat_configuration_missing", retryable=False)
        if self._create is None:
            raise ChatModelProviderFailure("chat_configuration_missing", retryable=False)
        return self._create

    def _parse_completion(self, response: object) -> ChatCompletionResult:
        choices = _sequence_value(response, "choices")
        if len(choices) != 1:
            raise ChatModelProviderFailure("chat_response_invalid", retryable=True)
        choice = choices[0]
        message = _value(choice, "message")
        content = _value(message, "content")
        if not isinstance(content, str) or not content.strip():
            raise ChatModelProviderFailure("chat_response_invalid", retryable=True)
        return ChatCompletionResult(
            content=content,
            model=_response_model(response, self._model_name),
            finish_reason=_optional_string(_value(choice, "finish_reason")),
            request_id=_optional_string(_value(response, "id")),
            usage=_parse_usage(_value(response, "usage")),
        )

    def _parse_stream_chunk(self, response: object) -> ChatStreamChunk | None:
        usage = _parse_usage(_value(response, "usage"))
        choices = _sequence_value(response, "choices")
        if not choices:
            if usage is None:
                return None
            return ChatStreamChunk(
                delta="",
                model=_response_model(response, self._model_name),
                finish_reason=None,
                request_id=_optional_string(_value(response, "id")),
                usage=usage,
            )
        if len(choices) != 1:
            raise ChatModelProviderFailure("chat_response_invalid", retryable=True)
        choice = choices[0]
        delta_container = _value(choice, "delta")
        delta = _value(delta_container, "content")
        if delta is None:
            delta = ""
        if not isinstance(delta, str):
            raise ChatModelProviderFailure("chat_response_invalid", retryable=True)
        finish_reason = _optional_string(_value(choice, "finish_reason"))
        if not delta and finish_reason is None and usage is None:
            return None
        return ChatStreamChunk(
            delta=delta,
            model=_response_model(response, self._model_name),
            finish_reason=finish_reason,
            request_id=_optional_string(_value(response, "id")),
            usage=usage,
        )


def _validated_messages(messages: Sequence[ChatMessage]) -> list[dict[str, str]]:
    if not messages:
        raise ChatModelProviderFailure("chat_input_invalid", retryable=False)
    payload: list[dict[str, str]] = []
    expected_role = ChatPromptRole.USER
    for index, message in enumerate(messages):
        if not isinstance(message, ChatMessage) or not message.content.strip():
            raise ChatModelProviderFailure("chat_input_invalid", retryable=False)
        if message.role == ChatPromptRole.SYSTEM:
            if index != 0:
                raise ChatModelProviderFailure("chat_input_invalid", retryable=False)
        elif message.role != expected_role:
            raise ChatModelProviderFailure("chat_input_invalid", retryable=False)
        else:
            expected_role = (
                ChatPromptRole.ASSISTANT
                if expected_role == ChatPromptRole.USER
                else ChatPromptRole.USER
            )
        payload.append({"role": message.role.value, "content": message.content})
    if messages[-1].role != ChatPromptRole.USER:
        raise ChatModelProviderFailure("chat_input_invalid", retryable=False)
    return payload


def _parse_usage(value: object) -> ChatTokenUsage | None:
    if value is None:
        return None
    try:
        prompt_tokens = int(_value(value, "prompt_tokens"))
        completion_tokens = int(_value(value, "completion_tokens"))
        total_tokens = int(_value(value, "total_tokens"))
    except (TypeError, ValueError) as exc:
        raise ChatModelProviderFailure("chat_response_invalid", retryable=True) from exc
    if (
        prompt_tokens < 0
        or completion_tokens < 0
        or total_tokens < 0
        or total_tokens != prompt_tokens + completion_tokens
    ):
        raise ChatModelProviderFailure("chat_response_invalid", retryable=True)
    return ChatTokenUsage(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
    )


def _provider_failure(exc: Exception) -> ChatModelProviderFailure:
    if isinstance(exc, APITimeoutError):
        return ChatModelProviderFailure("chat_provider_timeout", retryable=True)
    if isinstance(exc, (AuthenticationError, PermissionDeniedError)):
        return ChatModelProviderFailure("chat_provider_authentication_failed", retryable=False)
    if isinstance(exc, RateLimitError):
        return ChatModelProviderFailure("chat_provider_rate_limited", retryable=True)
    if isinstance(exc, APIConnectionError):
        return ChatModelProviderFailure("chat_provider_unavailable", retryable=True)
    status_code = getattr(exc, "status_code", None)
    if isinstance(exc, APIStatusError) or isinstance(status_code, int):
        retryable = status_code in {408, 409, 429} or (
            isinstance(status_code, int) and status_code >= 500
        )
        return ChatModelProviderFailure("chat_provider_rejected_request", retryable=retryable)
    return ChatModelProviderFailure("chat_provider_unavailable", retryable=True)


def _value(value: object, key: str, *, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        return value.get(key, default)
    return getattr(value, key, default)


def _sequence_value(value: object, key: str) -> Sequence[object]:
    result = _value(value, key)
    if not isinstance(result, Sequence) or isinstance(result, (str, bytes)):
        raise ChatModelProviderFailure("chat_response_invalid", retryable=True)
    return result


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ChatModelProviderFailure("chat_response_invalid", retryable=True)
    return value


def _response_model(response: object, fallback: str) -> str:
    model = _value(response, "model")
    if model is None:
        return fallback
    if not isinstance(model, str) or not model:
        raise ChatModelProviderFailure("chat_response_invalid", retryable=True)
    return model


def _as_async_iterator(value: object) -> AsyncIterator[object]:
    if not hasattr(value, "__aiter__"):
        raise ChatModelProviderFailure("chat_response_invalid", retryable=True)
    return cast(AsyncIterator[object], value)


async def _close_stream(value: object) -> None:
    close = getattr(value, "close", None)
    if close is None:
        return
    result = close()
    if inspect.isawaitable(result):
        await result


def as_chat_model_provider(provider: DashScopeChatModelProvider) -> ChatModelProvider:
    """让严格类型检查显式验证 Provider 协议实现。"""

    return provider
