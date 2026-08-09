"""最小知识库问答图使用的状态与结果类型。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal, TypedDict
from uuid import UUID

from app.agents.policies.finance_planner import AgentQuestionPlan
from app.agents.tools.finance import FinanceToolResult
from app.providers.model_provider import ChatCompletionResult
from app.rag.citations.structured import TrustedCitation
from app.services.retrieval import KnowledgeRetrievalResult, RetrievedChunk


@dataclass(frozen=True, slots=True)
class ControlledContextSource:
    """模型可见的临时来源编号及其后端可信映射。"""

    marker: str
    chunk: RetrievedChunk
    included_content: str
    truncated: bool


@dataclass(frozen=True, slots=True)
class ControlledRagContext:
    """有总长度上限、明确标记为不可信资料的模型上下文。"""

    serialized: str
    sources: tuple[ControlledContextSource, ...]


@dataclass(frozen=True, slots=True)
class RagAnswerResult:
    """一次最小 RAG 图运行的内部结果，供后续会话与引用层消费。"""

    owner_user_id: UUID
    question: str
    answer: str
    citations: tuple[TrustedCitation, ...]
    retrieval: KnowledgeRetrievalResult
    context: ControlledRagContext
    completion: ChatCompletionResult | None
    latency_ms: int
    checkpoint_id: str | None = None
    plan: AgentQuestionPlan | None = None
    finance_results: tuple[FinanceToolResult, ...] = ()
    data_as_of: datetime | None = None


@dataclass(frozen=True, slots=True)
class RagAnswerDelta:
    """模型生成期间向上层暴露的一段纯文本增量。"""

    text: str


@dataclass(frozen=True, slots=True)
class RagAnswerStage:
    """LangGraph 向聊天层暴露的有限用户可见阶段。"""

    stage: Literal[
        "understanding",
        "retrieving",
        "querying_finance",
        "analyzing",
        "generating",
        "finalizing",
    ]


@dataclass(frozen=True, slots=True)
class RagAnswerCompleted:
    """流式生成完成并通过可信引用校验后的最终结果。"""

    result: RagAnswerResult


type RagAnswerStreamEvent = RagAnswerStage | RagAnswerDelta | RagAnswerCompleted


class RagAnswerInput(TypedDict):
    """调用图时必须提供的输入。"""

    question: str
    retrieval_limit: int
    min_score: float | None
    response_mode: Literal["complete", "stream"]
    current_date: date


class RagAnswerOutput(TypedDict):
    """图对应用服务暴露的有限输出。"""

    retrieval: KnowledgeRetrievalResult
    context: ControlledRagContext
    completion: ChatCompletionResult | None
    answer: str
    citations: tuple[TrustedCitation, ...]
    plan: AgentQuestionPlan
    finance_results: tuple[FinanceToolResult, ...]


class RagAnswerState(TypedDict, total=False):
    """问答节点共享的完整状态；节点只返回自己产生的增量字段。"""

    question: str
    retrieval_limit: int
    min_score: float | None
    response_mode: Literal["complete", "stream"]
    current_date: date
    plan: AgentQuestionPlan
    planning_completion: ChatCompletionResult | None
    finance_results: tuple[FinanceToolResult, ...]
    retrieval: KnowledgeRetrievalResult
    context: ControlledRagContext
    completion: ChatCompletionResult | None
    answer: str
    citations: tuple[TrustedCitation, ...]


class RagAnswerUpdate(TypedDict, total=False):
    """节点状态更新类型。"""

    retrieval: KnowledgeRetrievalResult
    context: ControlledRagContext
    completion: ChatCompletionResult | None
    answer: str
    citations: tuple[TrustedCitation, ...]
    plan: AgentQuestionPlan
    planning_completion: ChatCompletionResult | None
    finance_results: tuple[FinanceToolResult, ...]
