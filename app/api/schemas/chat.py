"""面向普通登录用户的会话、消息与结构化引用契约。"""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.chat.types import AgentRunStatus, ConversationStatus, MessageRole, MessageStatus


class PageResponse(BaseModel):
    """列表接口共享的有界分页信息。"""

    page: int
    page_size: int
    total: int


class AvailableProjectResponse(BaseModel):
    """普通用户创建问答会话时可选择的最小项目信息。"""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    description: str | None


class AvailableProjectListResponse(BaseModel):
    """当前可用于基础 RAG 问答的项目列表。"""

    items: list[AvailableProjectResponse]


class ConversationCreate(BaseModel):
    """创建绑定到一个 Agent 项目的新会话。"""

    project_id: UUID
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
    project_id: UUID | None
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

    @field_validator("question")
    @classmethod
    def normalize_question(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("question must contain non-whitespace characters")
        return normalized


class CitationSourceSnapshot(BaseModel):
    """回答生成时冻结的来源身份与原文定位信息。"""

    document_id: UUID
    document_version_id: UUID
    knowledge_base_id: UUID
    chunk_id: UUID
    title: str = Field(min_length=1, max_length=512)
    document_version: int = Field(ge=1)
    page: int | None = Field(default=None, ge=1)
    section: str | None = Field(default=None, max_length=1024)
    sheet_name: str | None = Field(default=None, max_length=256)
    row_start: int | None = Field(default=None, ge=1)
    row_end: int | None = Field(default=None, ge=1)
    char_start: int | None = Field(default=None, ge=0)
    char_end: int | None = Field(default=None, ge=0)
    content_hash: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")

    @field_validator("title", mode="before")
    @classmethod
    def normalize_required_title(cls, value: object) -> object:
        """先清理必填标题，再由字段长度约束拒绝空白值。"""

        return value.strip() if isinstance(value, str) else value

    @field_validator("section", "sheet_name")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        """统一可选定位文本，同时保留缺失字段。"""

        normalized = value.strip() if value is not None else None
        return normalized or None

    @model_validator(mode="after")
    def validate_ranges(self) -> CitationSourceSnapshot:
        """拒绝无法定位回原文的倒置行号或字符范围。"""

        if self.row_start is not None and self.row_end is not None:
            if self.row_end < self.row_start:
                raise ValueError("row_end must be greater than or equal to row_start")
        if self.char_start is not None and self.char_end is not None:
            if self.char_end < self.char_start:
                raise ValueError("char_end must be greater than or equal to char_start")
        return self


class MessageCitationResponse(CitationSourceSnapshot):
    """一个由后端校验并编号的回答引用。"""

    citation_id: int = Field(ge=1)
    quote: str = Field(min_length=1)
    score: float | None = Field(default=None, ge=-1.0, le=1.0)

    @field_validator("quote", mode="before")
    @classmethod
    def normalize_quote(cls, value: object) -> object:
        """引用原文不得为空白。"""

        return value.strip() if isinstance(value, str) else value


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
    citations: list[MessageCitationResponse] = Field(default_factory=list)


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


class StructuredAnswerResponse(BaseModel):
    """非流式问答与 SSE 完成事件共享的最终载荷。"""

    message_id: UUID
    answer: str = Field(min_length=1)
    citations: list[MessageCitationResponse] = Field(default_factory=list)
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

    stage: Literal["retrieving", "generating", "finalizing"]


class StreamErrorResponse(BaseModel):
    """HTTP 响应已经开始后仍可安全传递的流式错误。"""

    code: str
    message: str
    request_id: str | None = None


class RunCancellationResponse(BaseModel):
    """显式停止生成后的运行标识与终态。"""

    run_id: UUID
    status: Literal["cancelled"]
