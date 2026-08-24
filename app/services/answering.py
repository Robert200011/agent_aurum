"""个人财务与长期记忆问答用例。"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, date, datetime
from time import perf_counter
from typing import Any, cast
from uuid import UUID
from zoneinfo import ZoneInfo

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import BaseCheckpointSaver

from app.agents.contracts import AgentQuestionPlan, ResponseDepthRequest
from app.agents.graph import AGENT_GRAPH_VERSION, build_answer_graph
from app.agents.state import (
    AnswerCompleted,
    AnswerDelta,
    AnswerInput,
    AnswerOutput,
    AnswerResult,
    AnswerStage,
    AnswerStreamEvent,
)
from app.agents.tools.finance import FinanceToolExecutor
from app.memory.retrieval import empty_memory_retrieval
from app.providers.model_provider import ChatModelProvider
from app.services.memory_retrieval import MemoryRetrievalService


class AnswerService:
    """使用会话 thread_id 运行带 PostgreSQL Checkpoint 的回答图。"""

    def __init__(
        self,
        *,
        owner_user_id: UUID,
        chat_provider: ChatModelProvider,
        finance_tools: FinanceToolExecutor | None = None,
        capability_agent_max_steps: int = 3,
        capability_agent_max_tool_calls: int = 6,
        memory_service: MemoryRetrievalService | None = None,
        finance_base_currency: str = "CNY",
        finance_timezone: str = "Asia/Shanghai",
        checkpointer: BaseCheckpointSaver[str] | None = None,
    ) -> None:
        self._owner_user_id = owner_user_id
        self._checkpoint_enabled = checkpointer is not None
        self._finance_timezone = finance_timezone
        self._graph = build_answer_graph(
            owner_user_id=owner_user_id,
            chat_provider=chat_provider,
            finance_tools=finance_tools,
            capability_agent_max_steps=capability_agent_max_steps,
            capability_agent_max_tool_calls=capability_agent_max_tool_calls,
            memory_service=memory_service,
            finance_base_currency=finance_base_currency,
            finance_timezone=finance_timezone,
            checkpointer=checkpointer,
        )

    async def answer(
        self,
        *,
        question: str,
        thread_id: UUID,
        history: list[dict[str, str]] | None = None,
        response_depth: ResponseDepthRequest = "auto",
    ) -> AnswerResult:
        started = perf_counter()
        graph_input = AnswerInput(
            question=question,
            response_mode="complete",
            current_date=_current_date(self._finance_timezone),
            history=history or [],
            response_depth=response_depth,
        )
        config = _graph_config(thread_id)
        output = cast(AnswerOutput, await self._graph.ainvoke(graph_input, config=config))
        return AnswerResult(
            owner_user_id=self._owner_user_id,
            question=question.strip(),
            answer=output["answer"],
            memory_retrieval=output["memory_retrieval"],
            completion=output["completion"],
            latency_ms=max(0, round((perf_counter() - started) * 1000)),
            checkpoint_id=await self._latest_checkpoint_id(config),
            plan=output["plan"],
            analysis_plan=output["analysis_plan"],
            answer_draft=output["answer_draft"],
            finance_results=output["finance_results"],
            data_as_of=_latest_finance_data_time(output["finance_results"]),
            capability_decision_steps=output["capability_decision_steps"],
            capability_call_count=output["capability_call_count"],
        )

    async def stream(
        self,
        *,
        question: str,
        thread_id: UUID,
        history: list[dict[str, str]] | None = None,
        response_depth: ResponseDepthRequest = "auto",
    ) -> AsyncIterator[AnswerStreamEvent]:
        started = perf_counter()
        graph_input = AnswerInput(
            question=question,
            response_mode="stream",
            current_date=_current_date(self._finance_timezone),
            history=history or [],
            response_depth=response_depth,
        )
        config = _graph_config(thread_id)
        output: AnswerOutput | None = None
        async for mode, data in self._graph.astream(
            graph_input,
            config=config,
            stream_mode=["custom", "values"],
        ):
            if mode == "custom":
                event = cast(dict[str, Any], data)
                if event.get("type") == "stage" and isinstance(event.get("stage"), str):
                    stage = cast(str, event["stage"])
                    if stage in {
                        "understanding",
                        "querying_finance",
                        "analyzing",
                        "generating",
                        "finalizing",
                    }:
                        yield AnswerStage(cast(Any, stage))
                elif event.get("type") == "answer_delta" and isinstance(event.get("text"), str):
                    yield AnswerDelta(cast(str, event["text"]))
            elif mode == "values":
                output = cast(AnswerOutput, data)
        if output is None:
            raise RuntimeError("answer graph stream ended without a final state")
        yield AnswerCompleted(
            AnswerResult(
                owner_user_id=self._owner_user_id,
                question=question.strip(),
                answer=output["answer"],
                memory_retrieval=output["memory_retrieval"],
                completion=output["completion"],
                latency_ms=max(0, round((perf_counter() - started) * 1000)),
                checkpoint_id=await self._latest_checkpoint_id(config),
                plan=output["plan"],
                analysis_plan=output["analysis_plan"],
                answer_draft=output["answer_draft"],
                finance_results=output["finance_results"],
                data_as_of=_latest_finance_data_time(output["finance_results"]),
                capability_decision_steps=output["capability_decision_steps"],
                capability_call_count=output["capability_call_count"],
            )
        )

    async def _latest_checkpoint_id(self, config: RunnableConfig) -> str | None:
        if not self._checkpoint_enabled:
            return None
        snapshot = await self._graph.aget_state(config)
        configurable = snapshot.config.get("configurable", {})
        checkpoint_id = configurable.get("checkpoint_id")
        return checkpoint_id if isinstance(checkpoint_id, str) else None


def build_memory_command_answer(*, owner_user_id: UUID, question: str) -> AnswerResult:
    """为已由记忆命令服务处理的消息构造无需再次调用模型的空回答结果。"""

    normalized_question = question.strip()
    return AnswerResult(
        owner_user_id=owner_user_id,
        question=normalized_question,
        answer="",
        memory_retrieval=empty_memory_retrieval(
            owner_user_id=owner_user_id,
            query=normalized_question,
        ),
        completion=None,
        latency_ms=0,
        plan=AgentQuestionPlan(
            intent="direct",
            needs_memory=False,
            route_reason="memory_command_service",
        ),
    )


def _graph_config(thread_id: UUID) -> RunnableConfig:
    return {
        "configurable": {
            "thread_id": str(thread_id),
            "checkpoint_ns": AGENT_GRAPH_VERSION,
        }
    }


def _current_date(timezone_name: str, *, at: datetime | None = None) -> date:
    current_time = at or datetime.now(UTC)
    if current_time.tzinfo is None:
        raise ValueError("current time must be timezone-aware")
    return current_time.astimezone(ZoneInfo(timezone_name)).date()


def _latest_finance_data_time(results: tuple[object, ...]) -> datetime | None:
    from app.agents.tools.finance import FinanceToolResult

    timestamps = [result.data_as_of for result in results if isinstance(result, FinanceToolResult)]
    return max(timestamps) if timestamps else None
