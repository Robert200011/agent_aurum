"""项目级 Dense 检索到 LLM 回答生成的最小 LangGraph。"""

from __future__ import annotations

from uuid import UUID

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.agents.policies.finance_planner import plan_agent_question
from app.agents.policies.rag_prompt import (
    NO_CONTEXT_ANSWER,
    apply_investment_risk_policy,
    build_answer_messages,
    build_controlled_context,
)
from app.agents.state import (
    RagAnswerInput,
    RagAnswerOutput,
    RagAnswerState,
    RagAnswerUpdate,
)
from app.agents.tools.finance import FinanceToolExecutor, FinanceToolStatus
from app.errors import ServiceUnavailableError
from app.providers.model_provider import (
    ChatCompletionResult,
    ChatModelProvider,
    ChatModelProviderError,
)
from app.rag.citations.structured import CitationValidationError, structure_citations
from app.services.retrieval import ProjectRetrievalResult, RagRetrievalService

RAG_GRAPH_VERSION = "finance-agent-p5.5-v1"
CompiledRagAnswerGraph = CompiledStateGraph[
    RagAnswerState,
    None,
    RagAnswerInput,
    RagAnswerOutput,
]


def build_rag_answer_graph(
    *,
    retrieval_service: RagRetrievalService,
    chat_provider: ChatModelProvider,
    context_max_characters: int,
    context_source_max_characters: int,
    finance_tools: FinanceToolExecutor | None = None,
    checkpointer: BaseCheckpointSaver[str] | None = None,
) -> CompiledRagAnswerGraph:
    """编译知识、财务与混合问题共用的受控 P5.5 回答图。"""

    def write_stage(state: RagAnswerState, stage: str) -> None:
        if state["response_mode"] == "stream":
            get_stream_writer()({"type": "stage", "stage": stage})

    def plan_question(state: RagAnswerState) -> RagAnswerUpdate:
        write_stage(state, "understanding")
        return {
            "plan": plan_agent_question(
                state["question"],
                today=state["current_date"],
            )
        }

    async def retrieve_knowledge(state: RagAnswerState) -> RagAnswerUpdate:
        plan = state["plan"]
        if not plan.needs_knowledge:
            return {
                "retrieval": _empty_retrieval(
                    project_id=state["project_id"],
                    question=state["question"],
                )
            }
        write_stage(state, "retrieving")
        retrieval = await retrieval_service.retrieve_project(
            project_id=state["project_id"],
            query=state["question"],
            limit=state["retrieval_limit"],
            min_score=state["min_score"],
        )
        return {"retrieval": retrieval}

    async def call_finance_tools(state: RagAnswerState) -> RagAnswerUpdate:
        requests = state["plan"].finance_calls
        if not requests:
            return {"finance_results": ()}
        if finance_tools is None:
            raise ServiceUnavailableError("finance agent tools are unavailable")
        write_stage(state, "querying_finance")
        return {"finance_results": await finance_tools.execute_many(requests)}

    async def generate_answer(state: RagAnswerState) -> RagAnswerUpdate:
        retrieval = state["retrieval"]
        context = build_controlled_context(
            retrieval.items,
            max_characters=context_max_characters,
            max_source_characters=context_source_max_characters,
        )
        plan = state["plan"]
        finance_results = state["finance_results"]
        write_stage(state, "analyzing")
        if plan.clarification is not None:
            return {
                "context": context,
                "completion": None,
                "answer": plan.clarification,
            }

        if plan.intent == "knowledge" and not context.sources:
            return {"context": context, "completion": None, "answer": NO_CONTEXT_ANSWER}
        if (
            plan.intent == "finance"
            and finance_results
            and all(result.status == FinanceToolStatus.FAILED for result in finance_results)
        ):
            return {
                "context": context,
                "completion": None,
                "answer": "当前无法读取所需的个人财务数据，请稍后重试。",
            }

        write_stage(state, "generating")
        messages = build_answer_messages(
            question=state["question"],
            context=context,
            finance_results=finance_results,
        )
        try:
            if state["response_mode"] == "stream":
                writer = get_stream_writer()
                parts: list[str] = []
                model = chat_provider.model_name
                finish_reason: str | None = None
                request_id: str | None = None
                usage = None
                async for chunk in chat_provider.stream(messages):
                    model = chunk.model
                    finish_reason = chunk.finish_reason or finish_reason
                    request_id = chunk.request_id or request_id
                    usage = chunk.usage or usage
                    if chunk.delta:
                        parts.append(chunk.delta)
                        writer({"type": "answer_delta", "text": chunk.delta})
                completion = ChatCompletionResult(
                    content="".join(parts).strip(),
                    model=model,
                    finish_reason=finish_reason,
                    request_id=request_id,
                    usage=usage,
                )
            else:
                completion = await chat_provider.complete(messages)
        except ChatModelProviderError as exc:
            message = (
                "chat model is not configured"
                if exc.code == "chat_configuration_missing"
                else "chat model provider is unavailable"
            )
            raise ServiceUnavailableError(message) from exc
        answer = completion.content.strip()
        if not answer:
            raise ServiceUnavailableError("chat model returned an invalid answer")
        return {
            "context": context,
            "completion": completion,
            "answer": answer,
        }

    def validate_citations(state: RagAnswerState) -> RagAnswerUpdate:
        write_stage(state, "finalizing")
        risk_checked_answer = apply_investment_risk_policy(
            state["answer"],
            risk_policy=state["plan"].risk_policy,
        )
        try:
            structured = structure_citations(
                answer=risk_checked_answer,
                context=state["context"],
                require_citation=bool(state["context"].sources),
            )
        except CitationValidationError as exc:
            raise ServiceUnavailableError(
                "chat model returned invalid citations"
            ) from exc
        return {
            "answer": structured.answer,
            "citations": structured.citations,
        }

    builder = StateGraph(
        RagAnswerState,
        input_schema=RagAnswerInput,
        output_schema=RagAnswerOutput,
    )
    builder.add_node("plan_question", plan_question)
    builder.add_node("retrieve_knowledge", retrieve_knowledge)
    builder.add_node("call_finance_tools", call_finance_tools)
    builder.add_node("generate_answer", generate_answer)
    builder.add_node("validate_citations", validate_citations)
    builder.add_edge(START, "plan_question")
    builder.add_edge("plan_question", "retrieve_knowledge")
    builder.add_edge("retrieve_knowledge", "call_finance_tools")
    builder.add_edge("call_finance_tools", "generate_answer")
    builder.add_edge("generate_answer", "validate_citations")
    builder.add_edge("validate_citations", END)
    return builder.compile(
        checkpointer=checkpointer,
        name=RAG_GRAPH_VERSION,
    )


def _empty_retrieval(*, project_id: UUID, question: str) -> ProjectRetrievalResult:
    return ProjectRetrievalResult(
        project_id=project_id,
        knowledge_base_ids=(),
        query=question.strip(),
        embedding_model="",
        latency_ms=0,
        items=[],
    )
