"""Authenticated-user contracts for personal knowledge resources."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class PageResponse(BaseModel):
    page: int
    page_size: int
    total: int


class KnowledgeBaseCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=10_000)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        return value.strip()

    @field_validator("description")
    @classmethod
    def normalize_description(cls, value: str | None) -> str | None:
        normalized = value.strip() if value is not None else None
        return normalized or None


class KnowledgeBaseUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=10_000)
    status: Annotated[str | None, Field(pattern=r"^(active|disabled)$")] = None
    search_enabled: bool | None = None

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else None

    @field_validator("description")
    @classmethod
    def normalize_description(cls, value: str | None) -> str | None:
        normalized = value.strip() if value is not None else None
        return normalized or None

    @model_validator(mode="after")
    def require_change(self) -> KnowledgeBaseUpdate:
        if not self.model_fields_set:
            raise ValueError("at least one knowledge-base field must be provided")
        return self


class KnowledgeBaseResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    description: str | None
    embedding_provider: str
    embedding_model: str
    embedding_dimensions: int
    embedding_distance_metric: str
    pipeline_version: str
    status: str
    search_enabled: bool
    created_at: datetime
    updated_at: datetime


class KnowledgeBaseListResponse(PageResponse):
    items: list[KnowledgeBaseResponse]


class RetrievalRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2_000)
    limit: int = Field(default=10, ge=1, le=50)
    min_score: float | None = Field(default=None, ge=-1.0, le=1.0)

    @field_validator("query")
    @classmethod
    def normalize_query(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("query must contain non-whitespace characters")
        return normalized


class RetrievedChunkResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    chunk_id: UUID
    document_id: UUID
    document_version_id: UUID
    knowledge_base_id: UUID
    content: str
    title: str
    page_number: int | None
    section_path: str | None
    sheet_name: str | None
    row_start: int | None
    row_end: int | None
    char_start: int | None
    char_end: int | None
    metadata: dict[str, Any]
    score: float
    retrieval_source: str


class RetrievalResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    knowledge_base_id: UUID
    query: str
    embedding_model: str
    latency_ms: int
    items: list[RetrievedChunkResponse]


class DocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    knowledge_base_id: UUID
    name: str
    mime_type: str
    size_bytes: int
    content_hash: str
    status: str
    is_enabled: bool
    created_at: datetime
    updated_at: datetime


class DocumentListResponse(PageResponse):
    items: list[DocumentResponse]


class DocumentVersionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    document_id: UUID
    version: int
    content_hash: str
    status: str
    pipeline_version: str
    embedding_provider: str
    embedding_model: str
    embedding_dimensions: int
    error_code: str | None
    error_message: str | None
    metadata_json: dict[str, str]
    created_at: datetime


class DocumentVersionListResponse(BaseModel):
    items: list[DocumentVersionResponse]


class DocumentDownloadUrlResponse(BaseModel):
    url: str
    expires_at: datetime


class IngestionJobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    document_id: UUID
    document_version_id: UUID
    status: str
    progress: int
    retry_count: int
    max_retries: int
    manual_retry_count: int
    error_code: str | None
    error_message: str | None
    error_detail: dict[str, Any] | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class IngestionJobListResponse(BaseModel):
    items: list[IngestionJobResponse]


class OutboxEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    ingestion_job_id: UUID
    status: str
    attempt_count: int
    max_attempts: int
    manual_retry_count: int
    available_at: datetime
    last_error: str | None
    published_at: datetime | None
    failed_at: datetime | None


class IngestionRetryResponse(BaseModel):
    ingestion_job: IngestionJobResponse
    dispatch_event: OutboxEventResponse


class DocumentUploadResponse(BaseModel):
    document: DocumentResponse
    version: DocumentVersionResponse
    ingestion_job: IngestionJobResponse
