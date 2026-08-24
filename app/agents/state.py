"""个人财务问答图使用的状态与结果类型。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal, TypedDict
from uuid import UUID

from app.agents.contracts import (
    AgentQuestionPlan,
    FinancialAnalysisPlan,
    FinancialAnswerDraft,
    ResponseDepthRequest,
)
from app.agents.tools.finance import FinanceToolResult
from app.memory.retrieval import MemoryRetrievalResult
from app.providers.model_provider import ChatCompletionResult


@dataclass(frozen=True, slots=True)
class AnswerResult:
    """一次财务问答图运行的内部结果。"""

    owner_user_id: UUID
    question: str
    answer: str
    memory_retrieval: MemoryRetrievalResult
    completion: ChatCompletionResult | None
    latency_ms: int
    checkpoint_id: str | None = None
    plan: AgentQuestionPlan | None = None
    analysis_plan: FinancialAnalysisPlan | None = None
    answer_draft: FinancialAnswerDraft | None = None
    finance_results: tuple[FinanceToolResult, ...] = ()
    data_as_of: datetime | None = None
    capability_decision_steps: int = 0
    capability_call_count: int = 0


@dataclass(frozen=True, slots=True)
class AnswerDelta:
    text: str


@dataclass(frozen=True, slots=True)
class AnswerStage:
    stage: Literal[
        "understanding",
        "querying_finance",
        "analyzing",
        "generating",
        "finalizing",
    ]


@dataclass(frozen=True, slots=True)
class AnswerCompleted:
    result: AnswerResult


type AnswerStreamEvent = AnswerStage | AnswerDelta | AnswerCompleted


class AnswerInput(TypedDict):
    question: str
    response_mode: Literal["complete", "stream"]
    current_date: date
    history: list[dict[str, str]]
    response_depth: ResponseDepthRequest


class AnswerOutput(TypedDict):
    memory_retrieval: MemoryRetrievalResult
    completion: ChatCompletionResult | None
    answer: str
    plan: AgentQuestionPlan
    analysis_plan: FinancialAnalysisPlan
    answer_draft: FinancialAnswerDraft
    finance_results: tuple[FinanceToolResult, ...]
    capability_decision_steps: int
    capability_call_count: int


class AnswerState(TypedDict, total=False):
    owner_user_id: UUID
    question: str
    response_mode: Literal["complete", "stream"]
    current_date: date
    history: list[dict[str, str]]
    response_depth: ResponseDepthRequest
    plan: AgentQuestionPlan
    analysis_plan: FinancialAnalysisPlan
    answer_draft: FinancialAnswerDraft
    finance_results: tuple[FinanceToolResult, ...]
    memory_retrieval: MemoryRetrievalResult
    completion: ChatCompletionResult | None
    answer: str
    capability_decision_steps: int
    capability_call_count: int


class AnswerUpdate(TypedDict, total=False):
    memory_retrieval: MemoryRetrievalResult
    completion: ChatCompletionResult | None
    answer: str
    plan: AgentQuestionPlan
    analysis_plan: FinancialAnalysisPlan
    answer_draft: FinancialAnswerDraft
    finance_results: tuple[FinanceToolResult, ...]
    capability_decision_steps: int
    capability_call_count: int
