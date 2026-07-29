"""Knowledge-base, document-ingestion, and retrieval persistence models."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
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
    IDENTITY_SCHEMA,
    RAG_SCHEMA,
    Base,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)
from app.rag.constants import (
    DASHSCOPE_EMBEDDING_PROVIDER,
    DASHSCOPE_TEXT_EMBEDDING_V4,
    DASHSCOPE_TEXT_EMBEDDING_V4_DIMENSIONS,
)


class AgentProject(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "agent_projects"
    __table_args__ = (Index("ix_agent_projects_status", "status"), {"schema": RAG_SCHEMA})

    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[UUID] = mapped_column(
        ForeignKey(f"{IDENTITY_SCHEMA}.users.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(24), default="active", nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class KnowledgeBase(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "knowledge_bases"
    __table_args__ = (
        CheckConstraint(
            "embedding_dimensions > 0", name="knowledge_base_embedding_dimensions_positive"
        ),
        CheckConstraint(
            "embedding_distance_metric IN ('cosine')",
            name="knowledge_base_distance_metric_valid",
        ),
        Index("ix_knowledge_bases_status", "status"),
        {"schema": RAG_SCHEMA},
    )

    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    embedding_provider: Mapped[str] = mapped_column(
        String(64), default=DASHSCOPE_EMBEDDING_PROVIDER, nullable=False
    )
    embedding_model: Mapped[str] = mapped_column(
        String(128), default=DASHSCOPE_TEXT_EMBEDDING_V4, nullable=False
    )
    embedding_dimensions: Mapped[int] = mapped_column(
        Integer, default=DASHSCOPE_TEXT_EMBEDDING_V4_DIMENSIONS, nullable=False
    )
    embedding_distance_metric: Mapped[str] = mapped_column(
        String(24), default="cosine", nullable=False
    )
    pipeline_version: Mapped[str] = mapped_column(String(64), default="v1", nullable=False)
    created_by: Mapped[UUID] = mapped_column(
        ForeignKey(f"{IDENTITY_SCHEMA}.users.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(24), default="draft", nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ProjectKnowledgeBase(Base):
    """Explicit project binding; the first binding establishes private ownership."""

    __tablename__ = "project_knowledge_bases"
    __table_args__ = ({"schema": RAG_SCHEMA},)

    project_id: Mapped[UUID] = mapped_column(
        ForeignKey(f"{RAG_SCHEMA}.agent_projects.id", ondelete="CASCADE"),
        primary_key=True,
    )
    knowledge_base_id: Mapped[UUID] = mapped_column(
        ForeignKey(f"{RAG_SCHEMA}.knowledge_bases.id", ondelete="CASCADE"),
        primary_key=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Document(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "documents"
    __table_args__ = (
        UniqueConstraint(
            "knowledge_base_id",
            "id",
            name="document_knowledge_base_identity",
        ),
        ForeignKeyConstraint(
            ["id", "current_published_version_id"],
            [
                f"{RAG_SCHEMA}.document_versions.document_id",
                f"{RAG_SCHEMA}.document_versions.id",
            ],
            name="fk_documents_current_published_version_same_document",
            use_alter=True,
            deferrable=True,
            initially="DEFERRED",
        ),
        Index("ix_documents_kb_status", "knowledge_base_id", "status"),
        Index("ix_documents_current_published_version", "current_published_version_id"),
        {"schema": RAG_SCHEMA},
    )

    knowledge_base_id: Mapped[UUID] = mapped_column(
        ForeignKey(f"{RAG_SCHEMA}.knowledge_bases.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(512), nullable=False)
    object_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(128), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    current_published_version_id: Mapped[UUID | None] = mapped_column()
    status: Mapped[str] = mapped_column(String(32), default="uploaded", nullable=False)
    is_enabled: Mapped[bool] = mapped_column(default=True, nullable=False)
    uploaded_by: Mapped[UUID] = mapped_column(
        ForeignKey(f"{IDENTITY_SCHEMA}.users.id", ondelete="RESTRICT"), nullable=False
    )
    disabled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DocumentVersion(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "document_versions"
    __table_args__ = (
        UniqueConstraint("document_id", "version", name="document_version_unique"),
        UniqueConstraint(
            "document_id",
            "id",
            name="document_version_document_identity",
        ),
        UniqueConstraint(
            "knowledge_base_id",
            "id",
            name="document_version_knowledge_base_identity",
        ),
        ForeignKeyConstraint(
            ["knowledge_base_id", "document_id"],
            [f"{RAG_SCHEMA}.documents.knowledge_base_id", f"{RAG_SCHEMA}.documents.id"],
            name="fk_document_versions_knowledge_base_document",
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "embedding_dimensions > 0", name="document_version_embedding_dimensions_positive"
        ),
        Index("ix_document_versions_document_status", "document_id", "status"),
        {"schema": RAG_SCHEMA},
    )

    document_id: Mapped[UUID] = mapped_column(nullable=False)
    knowledge_base_id: Mapped[UUID] = mapped_column(nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    source_object_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    parser_version: Mapped[str | None] = mapped_column(String(64))
    chunker_version: Mapped[str | None] = mapped_column(String(64))
    pipeline_version: Mapped[str] = mapped_column(String(64), default="v1", nullable=False)
    embedding_provider: Mapped[str] = mapped_column(String(64), nullable=False)
    embedding_model: Mapped[str] = mapped_column(String(128), nullable=False)
    embedding_dimensions: Mapped[int] = mapped_column(Integer, nullable=False)
    parsed_object_key: Mapped[str | None] = mapped_column(String(1024))
    status: Mapped[str] = mapped_column(String(32), default="queued", nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(Text)
    warnings: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, default=dict, nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class DocumentChunk(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "document_chunks"
    __table_args__ = (
        UniqueConstraint("document_version_id", "chunk_index", name="document_chunk_version_index"),
        ForeignKeyConstraint(
            ["knowledge_base_id", "document_version_id"],
            [
                f"{RAG_SCHEMA}.document_versions.knowledge_base_id",
                f"{RAG_SCHEMA}.document_versions.id",
            ],
            name="fk_document_chunks_knowledge_base_version",
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "char_end IS NULL OR char_start IS NULL OR char_end >= char_start",
            name="document_chunk_range_valid",
        ),
        Index("ix_document_chunks_kb_version", "knowledge_base_id", "document_version_id"),
        Index("ix_document_chunks_kb_content_hash", "knowledge_base_id", "content_hash"),
        Index(
            "ix_document_chunks_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
        {"schema": RAG_SCHEMA},
    )

    document_version_id: Mapped[UUID] = mapped_column(nullable=False)
    knowledge_base_id: Mapped[UUID] = mapped_column(nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    embedding: Mapped[list[float] | None] = mapped_column(
        Vector(DASHSCOPE_TEXT_EMBEDDING_V4_DIMENSIONS)
    )
    page_number: Mapped[int | None] = mapped_column(Integer)
    section_path: Mapped[str | None] = mapped_column(String(1024))
    sheet_name: Mapped[str | None] = mapped_column(String(256))
    row_start: Mapped[int | None] = mapped_column(Integer)
    row_end: Mapped[int | None] = mapped_column(Integer)
    char_start: Mapped[int | None] = mapped_column(Integer)
    char_end: Mapped[int | None] = mapped_column(Integer)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, default=dict, nullable=False
    )
    token_count: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class IngestionJob(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "ingestion_jobs"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="ingestion_job_idempotency_key"),
        ForeignKeyConstraint(
            ["document_id", "document_version_id"],
            [
                f"{RAG_SCHEMA}.document_versions.document_id",
                f"{RAG_SCHEMA}.document_versions.id",
            ],
            name="fk_ingestion_jobs_document_version_same_document",
            ondelete="CASCADE",
        ),
        CheckConstraint("progress BETWEEN 0 AND 100", name="ingestion_job_progress_valid"),
        CheckConstraint(
            "retry_count >= 0 AND max_retries >= 0 AND retry_count <= max_retries",
            name="ingestion_job_retry_count_valid",
        ),
        CheckConstraint(
            "manual_retry_count >= 0",
            name="ingestion_job_manual_retry_count_valid",
        ),
        Index("ix_ingestion_jobs_status_lease", "status", "lease_expires_at"),
        Index("ix_ingestion_jobs_document_version", "document_id", "document_version_id"),
        {"schema": RAG_SCHEMA},
    )

    document_id: Mapped[UUID] = mapped_column(nullable=False)
    document_version_id: Mapped[UUID] = mapped_column(nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="queued", nullable=False)
    progress: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_retries: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    manual_retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    lease_owner: Mapped[str | None] = mapped_column(String(128))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(Text)
    error_detail: Mapped[dict[str, Any] | None] = mapped_column(JSONB)


class DocumentUploadRequest(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Durable idempotency anchor created before object storage is contacted."""

    __tablename__ = "document_upload_requests"
    __table_args__ = (
        UniqueConstraint(
            "idempotency_key",
            name="document_upload_request_idempotency_key",
        ),
        UniqueConstraint(
            "ingestion_job_id",
            name="document_upload_request_ingestion_job",
        ),
        ForeignKeyConstraint(
            ["knowledge_base_id", "document_id"],
            [f"{RAG_SCHEMA}.documents.knowledge_base_id", f"{RAG_SCHEMA}.documents.id"],
            name="fk_document_upload_requests_knowledge_base_document",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["document_id", "document_version_id"],
            [
                f"{RAG_SCHEMA}.document_versions.document_id",
                f"{RAG_SCHEMA}.document_versions.id",
            ],
            name="fk_document_upload_requests_document_version",
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "target_type IN ('knowledge_base', 'document')",
            name="document_upload_request_target_type_valid",
        ),
        CheckConstraint(
            "status IN ('reserved', 'stored', 'activated', 'failed')",
            name="document_upload_request_status_valid",
        ),
        Index("ix_document_upload_requests_status_updated", "status", "updated_at"),
        {"schema": RAG_SCHEMA},
    )

    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    target_type: Mapped[str] = mapped_column(String(32), nullable=False)
    target_id: Mapped[UUID] = mapped_column(nullable=False)
    knowledge_base_id: Mapped[UUID] = mapped_column(nullable=False)
    document_id: Mapped[UUID] = mapped_column(nullable=False)
    document_version_id: Mapped[UUID] = mapped_column(nullable=False)
    ingestion_job_id: Mapped[UUID | None] = mapped_column(
        ForeignKey(f"{RAG_SCHEMA}.ingestion_jobs.id", ondelete="SET NULL")
    )
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(128), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    metadata_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="reserved", nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(64))
    error_detail: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_by: Mapped[UUID] = mapped_column(
        ForeignKey(f"{IDENTITY_SCHEMA}.users.id", ondelete="RESTRICT"),
        nullable=False,
    )


class OutboxEvent(UUIDPrimaryKeyMixin, Base):
    """Durable request to dispatch an ingestion job after transaction commit."""

    __tablename__ = "outbox_events"
    __table_args__ = (
        UniqueConstraint("ingestion_job_id", "event_type", name="outbox_event_job_type"),
        CheckConstraint(
            "status IN ('pending', 'published', 'failed')",
            name="outbox_event_status_valid",
        ),
        CheckConstraint(
            "attempt_count >= 0 AND max_attempts > 0 "
            "AND manual_retry_count >= 0 AND attempt_count <= max_attempts",
            name="outbox_event_attempt_count_valid",
        ),
        CheckConstraint(
            "(status = 'pending' AND published_at IS NULL AND failed_at IS NULL) OR "
            "(status = 'published' AND published_at IS NOT NULL AND failed_at IS NULL) OR "
            "(status = 'failed' AND published_at IS NULL AND failed_at IS NOT NULL)",
            name="outbox_event_state_consistent",
        ),
        Index("ix_outbox_events_pending", "status", "available_at"),
        Index("ix_outbox_events_lease", "lease_expires_at"),
        {"schema": RAG_SCHEMA},
    )

    ingestion_job_id: Mapped[UUID] = mapped_column(
        ForeignKey(f"{RAG_SCHEMA}.ingestion_jobs.id", ondelete="CASCADE"), nullable=False
    )
    event_type: Mapped[str] = mapped_column(String(128), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    status: Mapped[str] = mapped_column(String(24), default="pending", nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, default=8, nullable=False)
    manual_retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_error: Mapped[str | None] = mapped_column(Text)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_owner: Mapped[str | None] = mapped_column(String(128))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class RetrievalLog(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "retrieval_logs"
    __table_args__ = (
        Index("ix_retrieval_logs_user_created", "user_id", "created_at"),
        {"schema": RAG_SCHEMA},
    )

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey(f"{IDENTITY_SCHEMA}.users.id", ondelete="CASCADE"), nullable=False
    )
    knowledge_base_id: Mapped[UUID] = mapped_column(
        ForeignKey(f"{RAG_SCHEMA}.knowledge_bases.id", ondelete="CASCADE"), nullable=False
    )
    query: Mapped[str] = mapped_column(Text, nullable=False)
    result_count: Mapped[int] = mapped_column(Integer, nullable=False)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    top_score: Mapped[float | None] = mapped_column(Float)
    detail: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
