"""M3 记忆上下文预算和模型驱动只读召回测试。"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Sequence
from datetime import UTC, date, datetime
from typing import cast
from uuid import uuid4

import pytest

from app.agents.capabilities import MEMORY_SEARCH_CAPABILITY, CapabilityRegistry
from app.agents.capability_agent import run_capability_agent
from app.db.models.identity import MemoryCategory
from app.memory.retrieval import (
    MemoryRetrievalResult,
    RetrievedMemory,
    build_controlled_memory_context,
)
from app.providers.model_provider import (
    ChatCompletionResult,
    ChatMessage,
    ChatModelProvider,
    ChatStreamChunk,
    ChatToolCall,
    ChatToolCompletionResult,
    ChatToolDefinition,
    ChatToolExchange,
)
from app.services.memory_retrieval import MemoryRetrievalService
from app.services.retrieval import KnowledgeRetrievalResult, RagRetrievalService


def _memory(*, content: str, score: float = 0.9) -> RetrievedMemory:
    return RetrievedMemory(
        memory_id=uuid4(),
        category=MemoryCategory.GOAL,
        title="长期目标",
        content=content,
        content_hash="a" * 64,
        updated_at=datetime(2026, 8, 14, tzinfo=UTC),
        score=score,
        retrieval_source="dense",
    )


def test_memory_context_is_bounded_and_marks_user_provided_trust() -> None:
    context = build_controlled_memory_context(
        [_memory(content="甲" * 1_000), _memory(content="乙" * 1_000, score=0.8)],
        financial_profile={"occupation": "工程师", "currency": "CNY"},
        max_characters=500,
        max_item_characters=200,
    )
    payload = json.loads(context.serialized)

    assert len(context.serialized) <= 500
    assert payload["trust"] == "user_provided_memory"
    assert all(len(item["content"]) <= 200 for item in payload["memories"])
    assert "real-time financial evidence" in payload["notice"]


def test_memory_capability_has_no_user_scope_parameter() -> None:
    registry = CapabilityRegistry.read_only_default(
        finance_enabled=False,
        knowledge_enabled=False,
        memory_enabled=True,
    )
    definition = next(
        item for item in registry.definitions() if item.name == MEMORY_SEARCH_CAPABILITY
    )

    assert "user_id" not in definition.parameters.get("properties", {})
    assert registry.spec(MEMORY_SEARCH_CAPABILITY).side_effect == "none"


class _EmptyKnowledge:
    actor_user_id = uuid4()

    async def retrieve_user_knowledge(
        self,
        *,
        query: str,
        limit: int,
        min_score: float | None,
    ) -> KnowledgeRetrievalResult:
        del limit, min_score
        return KnowledgeRetrievalResult(
            owner_user_id=self.actor_user_id,
            knowledge_base_ids=(),
            query=query,
            embedding_model="",
            latency_ms=0,
            items=[],
        )


class _MemoryService:
    actor_user_id = _EmptyKnowledge.actor_user_id

    def __init__(self) -> None:
        self.queries: list[str] = []

    async def retrieve(
        self,
        *,
        query: str,
        category: MemoryCategory | None = None,
        limit: int | None = None,
    ) -> MemoryRetrievalResult:
        del category, limit
        self.queries.append(query)
        item = _memory(content="我希望三年内准备好购房首付")
        context = build_controlled_memory_context(
            [item],
            financial_profile={"occupation": "工程师", "currency": "CNY"},
            max_characters=1_000,
            max_item_characters=800,
        )
        return MemoryRetrievalResult(
            owner_user_id=self.actor_user_id,
            query=query,
            embedding_model="text-embedding-v4",
            latency_ms=2,
            items=(item,),
            financial_profile={"occupation": "工程师", "currency": "CNY"},
            context=context,
        )

    def combine(
        self,
        retrievals: list[MemoryRetrievalResult],
        *,
        query: str,
    ) -> MemoryRetrievalResult:
        del query
        return retrievals[0]


class _MemoryCallingModel:
    provider_name = "fake"
    model_name = "fake-memory-model"

    def __init__(self) -> None:
        self.calls = 0
        self.exchanges: Sequence[ChatToolExchange] = ()

    async def complete_with_tools(
        self,
        messages: Sequence[ChatMessage],
        tools: Sequence[ChatToolDefinition],
        *,
        require_tool: bool = False,
        exchanges: Sequence[ChatToolExchange] = (),
    ) -> ChatToolCompletionResult:
        del messages, tools, require_tool
        self.calls += 1
        self.exchanges = exchanges
        if self.calls == 1:
            return ChatToolCompletionResult(
                content=None,
                tool_calls=(
                    ChatToolCall(
                        "memory-call",
                        MEMORY_SEARCH_CAPABILITY,
                        {"query": "我的购房目标", "limit": 5},
                    ),
                ),
                model=self.model_name,
                finish_reason="tool_calls",
                request_id=None,
                usage=None,
            )
        return ChatToolCompletionResult(
            content="可以围绕三年购房首付目标安排储蓄。",
            tool_calls=(),
            model=self.model_name,
            finish_reason="stop",
            request_id=None,
            usage=None,
        )

    async def complete(self, messages: Sequence[ChatMessage]) -> ChatCompletionResult:
        raise AssertionError("memory tool flow should finish in the capability loop")

    def stream(self, messages: Sequence[ChatMessage]) -> AsyncIterator[ChatStreamChunk]:
        raise AssertionError("stream is not used")


@pytest.mark.asyncio
async def test_agent_uses_memory_only_after_model_requests_it() -> None:
    memory_service = _MemoryService()
    model = _MemoryCallingModel()

    outcome = await run_capability_agent(
        question="结合我的情况给一个储蓄方向",
        history=[],
        today=date(2026, 8, 14),
        retrieval_service=cast(RagRetrievalService, _EmptyKnowledge()),
        finance_tools=None,
        chat_provider=cast(ChatModelProvider, model),
        retrieval_limit=5,
        min_score=None,
        context_max_characters=2_000,
        context_source_max_characters=800,
        max_steps=3,
        max_tool_calls=5,
        memory_service=cast(MemoryRetrievalService, memory_service),
    )

    assert memory_service.queries == ["我的购房目标"]
    assert len(outcome.memory_retrieval.items) == 1
    assert outcome.plan.intent == "knowledge"
    assert model.exchanges
    observation = model.exchanges[0].results[0].content
    assert "user_provided_memory" in observation
    assert "memory_id" not in observation
