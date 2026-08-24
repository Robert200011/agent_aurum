"""面向普通登录用户的会话、消息与财务证据契约。"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.agents.contracts import AnalysisType, ResponseDepth, ResponseDepthRequest
from app.chat.types import AgentRunStatus, ConversationStatus, MessageRole, MessageStatus
from app.db.models.identity import MemoryCategory


class PageResponse(BaseModel):
    """列表接口共享的有界分页信息。"""

    page: int
    page_size: int
    total: int


class ConversationCreate(BaseModel):
    """创建不预先绑定知识范围的新会话。"""

    title: str | None = Field(default=None, max_length=256)

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: str | None) -> str | None:
        """空白标题交由服务层按首条问题生成。"""

        normalized = value.strip() if value is not None else None
        return normalized or None


class ConversationUpdate(BaseModel):
    """允许用户重命名或归档自己的会话。"""

    title: str | None = Field(default=None, min_length=1, max_length=256)
    status: ConversationStatus | None = None

    @field_validator("title", mode="before")
    @classmethod
    def normalize_title(cls, value: object) -> object:
        """避免存储仅由空白构成的展示标题。"""

        return value.strip() if isinstance(value, str) else value

    @model_validator(mode="after")
    def require_change(self) -> ConversationUpdate:
        """PATCH 至少需要提供一个可变字段。"""

        if not self.model_fields_set:
            raise ValueError("at least one conversation field must be provided")
        if "title" in self.model_fields_set and self.title is None:
            raise ValueError("conversation title cannot be null")
        if "status" in self.model_fields_set and self.status is None:
            raise ValueError("conversation status cannot be null")
        return self


class ConversationResponse(BaseModel):
    """不暴露租户字段的会话摘要。"""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    status: ConversationStatus
    created_at: datetime
    updated_at: datetime


class ConversationListResponse(PageResponse):
    """一页当前用户的会话。"""

    items: list[ConversationResponse]


class QuestionCreate(BaseModel):
    """向一个活跃会话提交的单轮问题。"""

    question: str = Field(min_length=1, max_length=2_000)
    response_depth: ResponseDepthRequest = "auto"

    @field_validator("question")
    @classmethod
    def normalize_question(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("question must contain non-whitespace characters")
        return normalized


class FinanceEvidenceFactResponse(BaseModel):
    """财务证据卡片中一个可读的数值事实。"""

    label: str = Field(min_length=1, max_length=64)
    value: str = Field(min_length=1, max_length=128)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    context: str | None = Field(default=None, max_length=256)


class MessageEvidenceResponse(BaseModel):
    """不伪装成文档引用的消息级财务证据。"""

    evidence_id: UUID
    tool_call_id: UUID
    rank: int = Field(ge=1)
    tool_name: str = Field(min_length=1, max_length=64)
    label: str = Field(min_length=1, max_length=128)
    data_as_of: datetime
    period_start: date | None = None
    period_end: date | None = None
    currencies: list[str] = Field(default_factory=list)
    calculation_basis: str = Field(min_length=1, max_length=512)
    facts: list[FinanceEvidenceFactResponse] = Field(default_factory=list)
    warning_codes: list[str] = Field(default_factory=list)


class MessageResponse(BaseModel):
    """可恢复的单条产品消息及其引用。"""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    conversation_id: UUID
    role: MessageRole
    content: str
    status: MessageStatus
    model: str | None
    prompt_tokens: int | None = Field(default=None, ge=0)
    completion_tokens: int | None = Field(default=None, ge=0)
    latency_ms: int | None = Field(default=None, ge=0)
    created_at: datetime
    evidence: list[MessageEvidenceResponse] = Field(default_factory=list)
    memory_count: int = Field(default=0, ge=0)
    data_as_of: datetime | None = None
    risk_notice: str | None = None


class ConversationDetailResponse(ConversationResponse):
    """会话摘要和按时间排序的历史消息。"""

    messages: list[MessageResponse] = Field(default_factory=list)


class AgentRunResponse(BaseModel):
    """用于故障诊断和流式状态恢复的运行摘要。"""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    conversation_id: UUID
    message_id: UUID | None
    thread_id: UUID
    trace_id: str | None
    status: AgentRunStatus
    graph_version: str | None
    error_code: str | None
    latency_ms: int | None = Field(default=None, ge=0)
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    finance_tool_count: int = Field(default=0, ge=0)
    data_as_of: datetime | None = None
    risk_notice: str | None = None
    analysis_type: AnalysisType | None = None
    response_depth: ResponseDepth | None = None
    fast_path: bool = False


class StructuredAnswerResponse(BaseModel):
    """非流式问答与 SSE 完成事件共享的最终载荷。"""

    message_id: UUID
    answer: str = Field(min_length=1)
    evidence: list[MessageEvidenceResponse] = Field(default_factory=list)
    memory_count: int = Field(default=0, ge=0)
    data_as_of: datetime | None = None
    risk_notice: str | None = None


class StreamStartedResponse(BaseModel):
    """SSE start 事件携带的持久化消息与运行标识。"""

    message_id: UUID
    run_id: UUID


class StreamDeltaResponse(BaseModel):
    """SSE delta 事件中的模型文本增量。"""

    delta: str = Field(min_length=1)


class StreamStatusResponse(BaseModel):
    """SSE status 事件中的稳定用户可见阶段。"""

    stage: Literal[
        "understanding",
        "querying_finance",
        "analyzing",
        "generating",
        "finalizing",
    ]


class StreamErrorResponse(BaseModel):
    """HTTP 响应已经开始后仍可安全传递的流式错误。"""

    code: str
    message: str
    request_id: str | None = None


class MemorySavedResponse(BaseModel):
    memory_id: UUID | None = None
    category: MemoryCategory
    title: str
    result: Literal["saved", "exists", "rejected"]
    reason: str | None = None


class MemoryConfirmationItemResponse(BaseModel):
    category: MemoryCategory
    title: str
    content: str


class MemoryConfirmationResponse(BaseModel):
    confirmation_id: UUID
    expires_at: datetime
    items: list[MemoryConfirmationItemResponse] = Field(min_length=1, max_length=5)


class MemoryConfirmationResolve(BaseModel):
    accept: bool


class MemoryConfirmationResolveResponse(BaseModel):
    status: Literal["accepted", "declined"]
    results: list[MemorySavedResponse] = Field(default_factory=list)


class RunCancellationResponse(BaseModel):
    """显式停止生成后的运行标识与终态。"""

    run_id: UUID
    status: Literal["cancelled"]
