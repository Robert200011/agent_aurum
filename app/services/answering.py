"""最小 LangGraph 知识库问答用例。"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, date, datetime
from time import perf_counter
from typing import Any, cast
from uuid import UUID
from zoneinfo import ZoneInfo

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import BaseCheckpointSaver

from app.agents.contracts import AgentQuestionPlan
from app.agents.graph import build_rag_answer_graph
from app.agents.policies.rag_prompt import build_controlled_context
from app.agents.state import (
    RagAnswerCompleted,
    RagAnswerDelta,
    RagAnswerInput,
    RagAnswerOutput,
    RagAnswerResult,
    RagAnswerStage,
    RagAnswerStreamEvent,
)
from app.agents.tools.finance import FinanceToolExecutor
from app.memory.retrieval import empty_memory_retrieval
from app.providers.model_provider import ChatModelProvider
from app.services.memory_retrieval import MemoryRetrievalService
from app.services.retrieval import KnowledgeRetrievalResult, RagRetrievalService


class RagAnswerService:
    """使用会话 thread_id 运行带 PostgreSQL Checkpoint 的基础 RAG 图。"""

    def __init__(
        self,
        *,
        retrieval_service: RagRetrievalService,
        chat_provider: ChatModelProvider,
        retrieval_limit: int,
        context_max_characters: int,
        context_source_max_characters: int,
        finance_tools: FinanceToolExecutor | None = None,
        capability_agent_max_steps: int = 3,
        capability_agent_max_tool_calls: int = 6,
        memory_service: MemoryRetrievalService | None = None,
        finance_base_currency: str = "CNY",
        finance_timezone: str = "Asia/Shanghai",
        checkpointer: BaseCheckpointSaver[str] | None = None,
    ) -> None:
        self._checkpoint_enabled = checkpointer is not None
        self._retrieval_limit = retrieval_limit
        self._retrieval_service = retrieval_service
        self._chat_provider = chat_provider
        self._context_max_characters = context_max_characters
        self._context_source_max_characters = context_source_max_characters
        self._finance_timezone = finance_timezone
        self._graph = build_rag_answer_graph(
            retrieval_service=retrieval_service,
            chat_provider=chat_provider,
            context_max_characters=context_max_characters,
            context_source_max_characters=context_source_max_characters,
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
    ) -> RagAnswerResult:
        """执行单轮项目问答；结构化引用和消息落库由下一步接入。"""

        started = perf_counter()
        graph_input = RagAnswerInput(
            question=question,
            retrieval_limit=self._retrieval_limit,
            min_score=None,
            response_mode="complete",
            current_date=_current_date(self._finance_timezone),
            history=history or [],
        )
        config = _graph_config(thread_id)
        output = cast(
            RagAnswerOutput,
            await self._graph.ainvoke(graph_input, config=config),
        )
        latency_ms = max(0, round((perf_counter() - started) * 1000))
        retrieval = output["retrieval"]
        return RagAnswerResult(
            owner_user_id=output["retrieval"].owner_user_id,
            question=retrieval.query,
            answer=output["answer"],
            citations=output["citations"],
            retrieval=retrieval,
            context=output["context"],
            memory_retrieval=output["memory_retrieval"],
            completion=output["completion"],
            latency_ms=latency_ms,
            checkpoint_id=await self._latest_checkpoint_id(config),
            plan=output["plan"],
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
    ) -> AsyncIterator[RagAnswerStreamEvent]:
        """通过 LangGraph custom stream 转发模型文本并保存每个节点恢复点。"""

        started = perf_counter()
        graph_input = RagAnswerInput(
            question=question,
            retrieval_limit=self._retrieval_limit,
            min_score=None,
            response_mode="stream",
            current_date=_current_date(self._finance_timezone),
            history=history or [],
        )
        config = _graph_config(thread_id)
        output: RagAnswerOutput | None = None
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
                        "retrieving",
                        "querying_finance",
                        "analyzing",
                        "generating",
                        "finalizing",
                    }:
                        yield RagAnswerStage(cast(Any, stage))
                elif event.get("type") == "answer_delta" and isinstance(event.get("text"), str):
                    yield RagAnswerDelta(cast(str, event["text"]))
            elif mode == "values":
                output = cast(RagAnswerOutput, data)
        if output is None:
            raise RuntimeError("RAG graph stream ended without a final state")
        retrieval = output["retrieval"]
        yield RagAnswerCompleted(
            RagAnswerResult(
                owner_user_id=output["retrieval"].owner_user_id,
                question=retrieval.query,
                answer=output["answer"],
                citations=output["citations"],
                retrieval=retrieval,
                context=output["context"],
                memory_retrieval=output["memory_retrieval"],
                completion=output["completion"],
                latency_ms=max(0, round((perf_counter() - started) * 1000)),
                checkpoint_id=await self._latest_checkpoint_id(config),
                plan=output["plan"],
                finance_results=output["finance_results"],
                data_as_of=_latest_finance_data_time(output["finance_results"]),
                capability_decision_steps=output["capability_decision_steps"],
                capability_call_count=output["capability_call_count"],
            )
        )

    async def _latest_checkpoint_id(self, config: RunnableConfig) -> str | None:
        """读取刚完成图运行的最终 checkpoint_id，供 AgentRun 关联诊断。"""

        if not self._checkpoint_enabled:
            return None
        snapshot = await self._graph.aget_state(config)
        configurable = snapshot.config.get("configurable", {})
        checkpoint_id = configurable.get("checkpoint_id")
        return checkpoint_id if isinstance(checkpoint_id, str) else None


def build_memory_command_answer(*, owner_user_id: UUID, question: str) -> RagAnswerResult:
    """为已由记忆命令服务处理的消息构造无需再次调用模型的空回答结果。"""

    normalized_question = question.strip()
    retrieval = KnowledgeRetrievalResult(
        owner_user_id=owner_user_id,
        knowledge_base_ids=(),
        query=normalized_question,
        embedding_model="",
        latency_ms=0,
        items=[],
    )
    return RagAnswerResult(
        owner_user_id=owner_user_id,
        question=normalized_question,
        answer="",
        citations=(),
        retrieval=retrieval,
        context=build_controlled_context(
            [],
            max_characters=500,
            max_source_characters=100,
        ),
        memory_retrieval=empty_memory_retrieval(
            owner_user_id=owner_user_id,
            query=normalized_question,
        ),
        completion=None,
        latency_ms=0,
        plan=AgentQuestionPlan(
            intent="direct",
            needs_knowledge=False,
            route_reason="memory_command_service",
        ),
    )


def _graph_config(thread_id: UUID) -> RunnableConfig:
    return {
        "configurable": {
            "thread_id": str(thread_id),
            "checkpoint_ns": "",
        }
    }


def _current_date(timezone_name: str, *, at: datetime | None = None) -> date:
    """使用当前用户的 IANA 时区解析相对日期。"""

    current_time = at or datetime.now(UTC)
    if current_time.tzinfo is None:
        raise ValueError("current time must be timezone-aware")
    return current_time.astimezone(ZoneInfo(timezone_name)).date()


def _latest_finance_data_time(results: tuple[object, ...]) -> datetime | None:
    from app.agents.tools.finance import FinanceToolResult

    timestamps = [result.data_as_of for result in results if isinstance(result, FinanceToolResult)]
    return max(timestamps) if timestamps else None
