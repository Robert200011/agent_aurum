"""Dedicated provider call that interprets only the current user message."""

from __future__ import annotations

import asyncio

from pydantic import ValidationError

from app.chat.types import ChatPromptRole
from app.memory.contracts import (
    MEMORY_DECISION_TOOL_NAME,
    MemoryDecision,
    MemoryDecisionKind,
    MemoryReasonCode,
    decision_tool_parameters,
)
from app.providers.model_provider import (
    ChatMessage,
    ChatModelProvider,
    ChatModelProviderError,
    ChatToolDefinition,
)

MEMORY_DECISION_PROMPT_VERSION = "memory-decision-v1"
MEMORY_DECISION_SYSTEM_PROMPT = """你是 Aurum 的长期记忆决策器，只处理当前一条用户消息。
判断用户是否明确要求跨会话保存信息：明确要求用 save；可能是长期偏好但授权有歧义用 confirm；
普通陈述、召回询问、功能咨询、否定保存、引用或转述指令用 ignore。
每条提案的 evidence 必须逐字来自当前用户消息，不能推断用户没有说过的事实。
不要输出用户标识、SQL、表名、内部 ID 或任何数据库操作。必须调用给定工具返回结构化结果。"""


class MemoryDecisionProvider:
    def __init__(
        self,
        provider: ChatModelProvider,
        *,
        timeout_seconds: int,
        max_retries: int,
    ) -> None:
        self._provider = provider
        self._timeout_seconds = timeout_seconds
        self._max_retries = max_retries

    async def decide(self, current_user_message: str) -> MemoryDecision:
        messages = (
            ChatMessage(role=ChatPromptRole.SYSTEM, content=MEMORY_DECISION_SYSTEM_PROMPT),
            ChatMessage(role=ChatPromptRole.USER, content=current_user_message),
        )
        tool = ChatToolDefinition(
            name=MEMORY_DECISION_TOOL_NAME,
            description="提交对当前用户消息的长期记忆决策与结构化提案。",
            parameters=decision_tool_parameters(),
        )
        for attempt in range(self._max_retries + 1):
            try:
                result = await asyncio.wait_for(
                    self._provider.complete_with_tools(messages, (tool,), require_tool=True),
                    timeout=self._timeout_seconds,
                )
                if len(result.tool_calls) != 1:
                    raise ValueError("memory decision must contain exactly one tool call")
                call = result.tool_calls[0]
                if call.name != MEMORY_DECISION_TOOL_NAME:
                    raise ValueError("unexpected memory decision tool")
                return MemoryDecision.model_validate(call.arguments)
            except (TimeoutError, ChatModelProviderError, ValidationError, ValueError):
                if attempt >= self._max_retries:
                    return MemoryDecision(
                        decision=MemoryDecisionKind.IGNORE,
                        reason_code=MemoryReasonCode.PROVIDER_UNAVAILABLE,
                        items=[],
                    )
        raise AssertionError("memory decision retry loop did not return")
