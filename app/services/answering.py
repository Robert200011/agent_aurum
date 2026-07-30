"""最小 LangGraph 知识库问答用例。"""

from __future__ import annotations

from time import perf_counter
from typing import cast
from uuid import UUID

from app.agents.graph import build_rag_answer_graph
from app.agents.state import RagAnswerInput, RagAnswerOutput, RagAnswerResult
from app.providers.model_provider import ChatModelProvider
from app.services.retrieval import RagRetrievalService


class RagAnswerService:
    """运行无 Checkpoint 的基础 RAG 图，返回后续持久化所需的内部结果。"""

    def __init__(
        self,
        *,
        retrieval_service: RagRetrievalService,
        chat_provider: ChatModelProvider,
        retrieval_limit: int,
        context_max_characters: int,
        context_source_max_characters: int,
    ) -> None:
        self._retrieval_limit = retrieval_limit
        self._graph = build_rag_answer_graph(
            retrieval_service=retrieval_service,
            chat_provider=chat_provider,
            context_max_characters=context_max_characters,
            context_source_max_characters=context_source_max_characters,
        )

    async def answer(self, *, project_id: UUID, question: str) -> RagAnswerResult:
        """执行单轮项目问答；结构化引用和消息落库由下一步接入。"""

        started = perf_counter()
        graph_input = RagAnswerInput(
            project_id=project_id,
            question=question,
            retrieval_limit=self._retrieval_limit,
            min_score=None,
        )
        output = cast(RagAnswerOutput, await self._graph.ainvoke(graph_input))
        latency_ms = max(0, round((perf_counter() - started) * 1000))
        retrieval = output["retrieval"]
        return RagAnswerResult(
            project_id=project_id,
            question=retrieval.query,
            answer=output["answer"],
            citations=output["citations"],
            retrieval=retrieval,
            context=output["context"],
            completion=output["completion"],
            latency_ms=latency_ms,
        )
