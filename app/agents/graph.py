"""项目级 Dense 检索到 LLM 回答生成的最小 LangGraph。"""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.agents.policies.rag_prompt import (
    NO_CONTEXT_ANSWER,
    build_answer_messages,
    build_controlled_context,
)
from app.agents.state import (
    RagAnswerInput,
    RagAnswerOutput,
    RagAnswerState,
    RagAnswerUpdate,
)
from app.errors import ServiceUnavailableError
from app.providers.model_provider import ChatModelProvider, ChatModelProviderError
from app.rag.citations.structured import CitationValidationError, structure_citations
from app.services.retrieval import RagRetrievalService

RAG_GRAPH_VERSION = "rag-citations-v1"
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
) -> CompiledRagAnswerGraph:
    """编译检索、生成和可信引用校验三个固定节点。"""

    async def retrieve_knowledge(state: RagAnswerState) -> RagAnswerUpdate:
        retrieval = await retrieval_service.retrieve_project(
            project_id=state["project_id"],
            query=state["question"],
            limit=state["retrieval_limit"],
            min_score=state["min_score"],
        )
        return {"retrieval": retrieval}

    async def generate_answer(state: RagAnswerState) -> RagAnswerUpdate:
        retrieval = state["retrieval"]
        context = build_controlled_context(
            retrieval.items,
            max_characters=context_max_characters,
            max_source_characters=context_source_max_characters,
        )
        if not context.sources:
            return {
                "context": context,
                "completion": None,
                "answer": NO_CONTEXT_ANSWER,
            }

        try:
            completion = await chat_provider.complete(
                build_answer_messages(question=state["question"], context=context)
            )
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
        try:
            structured = structure_citations(
                answer=state["answer"],
                context=state["context"],
                require_citation=state["completion"] is not None,
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
    builder.add_node("retrieve_knowledge", retrieve_knowledge)
    builder.add_node("generate_answer", generate_answer)
    builder.add_node("validate_citations", validate_citations)
    builder.add_edge(START, "retrieve_knowledge")
    builder.add_edge("retrieve_knowledge", "generate_answer")
    builder.add_edge("generate_answer", "validate_citations")
    builder.add_edge("validate_citations", END)
    return builder.compile(name=RAG_GRAPH_VERSION)
