"""Product conversations, citations, and agent execution metadata."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import (
    CHAT_SCHEMA,
    IDENTITY_SCHEMA,
    RAG_SCHEMA,
    Base,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)


class Conversation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "conversations"
    __table_args__ = (
        UniqueConstraint("id", "user_id", name="conversation_user_identity"),
        CheckConstraint(
            "status IN ('active', 'archived')",
            name="conversation_status_valid",
        ),
        Index("ix_conversations_user_updated", "user_id", "updated_at"),
        {"schema": CHAT_SCHEMA},
    )

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey(f"{IDENTITY_SCHEMA}.users.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="active", nullable=False)


class Message(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "messages"
    __table_args__ = (
        UniqueConstraint("id", "user_id", name="message_user_identity"),
        ForeignKeyConstraint(
            ["conversation_id", "user_id"],
            [f"{CHAT_SCHEMA}.conversations.id", f"{CHAT_SCHEMA}.conversations.user_id"],
            name="fk_messages_conversation_user",
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "role IN ('user', 'assistant')",
            name="message_role_valid",
        ),
        CheckConstraint(
            "status IN ('pending', 'streaming', 'completed', 'failed', 'cancelled')",
            name="message_status_valid",
        ),
        CheckConstraint(
            "(prompt_tokens IS NULL OR prompt_tokens >= 0) "
            "AND (completion_tokens IS NULL OR completion_tokens >= 0) "
            "AND (latency_ms IS NULL OR latency_ms >= 0)",
            name="message_metrics_nonnegative",
        ),
        Index("ix_messages_conversation_created", "conversation_id", "created_at"),
        Index("ix_messages_user_created", "user_id", "created_at"),
        {"schema": CHAT_SCHEMA},
    )

    conversation_id: Mapped[UUID] = mapped_column(
        ForeignKey(f"{CHAT_SCHEMA}.conversations.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey(f"{IDENTITY_SCHEMA}.users.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(24), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="completed", nullable=False)
    model: Mapped[str | None] = mapped_column(String(128))
    prompt_tokens: Mapped[int | None] = mapped_column(Integer)
    completion_tokens: Mapped[int | None] = mapped_column(Integer)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class MessageCitation(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "message_citations"
    __table_args__ = (
        ForeignKeyConstraint(
            ["message_id", "user_id"],
            [f"{CHAT_SCHEMA}.messages.id", f"{CHAT_SCHEMA}.messages.user_id"],
            name="fk_message_citations_message_user",
            ondelete="CASCADE",
        ),
        CheckConstraint("rank > 0", name="message_citation_rank_positive"),
        CheckConstraint(
            "score IS NULL OR score BETWEEN -1.0 AND 1.0",
            name="message_citation_score_valid",
        ),
        CheckConstraint(
            "jsonb_typeof(source_snapshot) = 'object' "
            "AND source_snapshot ?& ARRAY["
            "'document_id', 'document_version_id', 'knowledge_base_id', "
            "'chunk_id', 'title', 'document_version', 'content_hash'"
            "] "
            "AND source_snapshot ->> 'chunk_id' = chunk_id::text "
            "AND length(btrim(source_snapshot ->> 'title')) > 0",
            name="message_citation_source_snapshot_valid",
        ),
        Index("ix_message_citations_message_rank", "message_id", "rank", unique=True),
        {"schema": CHAT_SCHEMA},
    )

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey(f"{IDENTITY_SCHEMA}.users.id", ondelete="CASCADE"), nullable=False
    )
    message_id: Mapped[UUID] = mapped_column(
        ForeignKey(f"{CHAT_SCHEMA}.messages.id", ondelete="CASCADE"), nullable=False
    )
    chunk_id: Mapped[UUID] = mapped_column(
        ForeignKey(f"{RAG_SCHEMA}.document_chunks.id", ondelete="RESTRICT"), nullable=False
    )
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    score: Mapped[float | None] = mapped_column(Float)
    quote_snapshot: Mapped[str] = mapped_column(Text, nullable=False)
    source_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)


class AgentRun(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "agent_runs"
    __table_args__ = (
        UniqueConstraint("id", "user_id", name="agent_run_user_identity"),
        ForeignKeyConstraint(
            ["conversation_id", "user_id"],
            [f"{CHAT_SCHEMA}.conversations.id", f"{CHAT_SCHEMA}.conversations.user_id"],
            name="fk_agent_runs_conversation_user",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["message_id", "user_id"],
            [f"{CHAT_SCHEMA}.messages.id", f"{CHAT_SCHEMA}.messages.user_id"],
            name="fk_agent_runs_message_user",
        ),
        CheckConstraint(
            "status IN ('queued', 'running', 'completed', 'failed', 'cancelled')",
            name="agent_run_status_valid",
        ),
        CheckConstraint(
            "latency_ms IS NULL OR latency_ms >= 0",
            name="agent_run_latency_nonnegative",
        ),
        CheckConstraint(
            "thread_id = conversation_id",
            name="agent_run_thread_matches_conversation",
        ),
        Index("ix_agent_runs_conversation_created", "conversation_id", "created_at"),
        {"schema": CHAT_SCHEMA},
    )

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey(f"{IDENTITY_SCHEMA}.users.id", ondelete="CASCADE"), nullable=False
    )
    conversation_id: Mapped[UUID] = mapped_column(
        ForeignKey(f"{CHAT_SCHEMA}.conversations.id", ondelete="CASCADE"), nullable=False
    )
    message_id: Mapped[UUID | None] = mapped_column(
        ForeignKey(f"{CHAT_SCHEMA}.messages.id", ondelete="SET NULL")
    )
    thread_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    trace_id: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    graph_version: Mapped[str | None] = mapped_column(String(64))
    error_code: Mapped[str | None] = mapped_column(String(64))
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    detail: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class AgentRunMemory(UUIDPrimaryKeyMixin, Base):
    """一次回答实际调用的记忆标识与脱敏排序信息。"""

    __tablename__ = "agent_run_memories"
    __table_args__ = (
        ForeignKeyConstraint(
            ["agent_run_id", "user_id"],
            [f"{CHAT_SCHEMA}.agent_runs.id", f"{CHAT_SCHEMA}.agent_runs.user_id"],
            name="fk_agent_run_memories_run_user",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["memory_id", "user_id"],
            [f"{IDENTITY_SCHEMA}.user_memories.id", f"{IDENTITY_SCHEMA}.user_memories.user_id"],
            name="fk_agent_run_memories_memory_user",
            ondelete="CASCADE",
        ),
        UniqueConstraint("agent_run_id", "memory_id", name="agent_run_memory_identity"),
        CheckConstraint("rank > 0", name="agent_run_memory_rank_positive"),
        CheckConstraint(
            "relevance_score IS NULL OR relevance_score BETWEEN -1.0 AND 1.0",
            name="agent_run_memory_relevance_score_valid",
        ),
        CheckConstraint(
            "content_hash ~ '^[0-9a-f]{64}$'", name="agent_run_memory_content_hash_valid"
        ),
        Index("ix_agent_run_memories_run_rank", "agent_run_id", "rank", unique=True),
        {"schema": CHAT_SCHEMA},
    )

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey(f"{IDENTITY_SCHEMA}.users.id", ondelete="CASCADE"), nullable=False
    )
    agent_run_id: Mapped[UUID] = mapped_column(nullable=False)
    memory_id: Mapped[UUID] = mapped_column(nullable=False)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    relevance_score: Mapped[float | None] = mapped_column(Float)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    memory_updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class AgentToolCall(UUIDPrimaryKeyMixin, Base):
    """一次只读 Agent 工具调用的脱敏审计记录。"""

    __tablename__ = "agent_tool_calls"
    __table_args__ = (
        UniqueConstraint("id", "user_id", name="agent_tool_call_user_identity"),
        ForeignKeyConstraint(
            ["run_id", "user_id"],
            [f"{CHAT_SCHEMA}.agent_runs.id", f"{CHAT_SCHEMA}.agent_runs.user_id"],
            name="fk_agent_tool_calls_run_user",
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "status IN ('succeeded', 'failed')",
            name="agent_tool_call_status_valid",
        ),
        CheckConstraint(
            "duration_ms >= 0",
            name="agent_tool_call_duration_nonnegative",
        ),
        CheckConstraint(
            "jsonb_typeof(arguments) = 'object'",
            name="agent_tool_call_arguments_object",
        ),
        CheckConstraint(
            "jsonb_typeof(result_summary) = 'object'",
            name="agent_tool_call_result_summary_object",
        ),
        CheckConstraint(
            "result_hash ~ '^[0-9a-f]{64}$'",
            name="agent_tool_call_result_hash_valid",
        ),
        Index("ix_agent_tool_calls_run_created", "run_id", "created_at"),
        Index("ix_agent_tool_calls_run_call", "run_id", "call_id", unique=True),
        {"schema": CHAT_SCHEMA},
    )

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey(f"{IDENTITY_SCHEMA}.users.id", ondelete="CASCADE"), nullable=False
    )
    run_id: Mapped[UUID] = mapped_column(nullable=False)
    call_id: Mapped[UUID] = mapped_column(nullable=False)
    tool_name: Mapped[str] = mapped_column(String(64), nullable=False)
    arguments: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    data_as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    result_summary: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    result_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class MessageEvidence(UUIDPrimaryKeyMixin, Base):
    """回答使用的消息级财务事实快照及其工具来源。"""

    __tablename__ = "message_evidence"
    __table_args__ = (
        ForeignKeyConstraint(
            ["message_id", "user_id"],
            [f"{CHAT_SCHEMA}.messages.id", f"{CHAT_SCHEMA}.messages.user_id"],
            name="fk_message_evidence_message_user",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tool_call_id", "user_id"],
            [
                f"{CHAT_SCHEMA}.agent_tool_calls.id",
                f"{CHAT_SCHEMA}.agent_tool_calls.user_id",
            ],
            name="fk_message_evidence_tool_call_user",
            ondelete="CASCADE",
        ),
        CheckConstraint("rank > 0", name="message_evidence_rank_positive"),
        CheckConstraint(
            "evidence_type = 'finance'",
            name="message_evidence_type_valid",
        ),
        CheckConstraint(
            "jsonb_typeof(evidence_snapshot) = 'object' "
            "AND evidence_snapshot ?& ARRAY["
            "'tool_name', 'label', 'data_as_of', 'calculation_basis', "
            "'currencies', 'facts', 'warning_codes'"
            "]",
            name="message_evidence_snapshot_valid",
        ),
        Index("ix_message_evidence_message_rank", "message_id", "rank", unique=True),
        {"schema": CHAT_SCHEMA},
    )

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey(f"{IDENTITY_SCHEMA}.users.id", ondelete="CASCADE"), nullable=False
    )
    message_id: Mapped[UUID] = mapped_column(nullable=False)
    tool_call_id: Mapped[UUID] = mapped_column(nullable=False)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    evidence_type: Mapped[str] = mapped_column(String(24), nullable=False)
    evidence_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
