"""Administrator-only API contracts for projects and knowledge bases."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class PageResponse(BaseModel):
    page: int
    page_size: int
    total: int


class ProjectCreate(BaseModel):
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


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=10_000)
    status: Annotated[str | None, Field(pattern=r"^(active|disabled)$")] = None

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
    def require_change(self) -> ProjectUpdate:
        if not self.model_fields_set:
            raise ValueError("at least one project field must be provided")
        return self


class ProjectResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    description: str | None
    status: str
    created_at: datetime
    updated_at: datetime


class ProjectListResponse(PageResponse):
    items: list[ProjectResponse]


class KnowledgeBaseCreate(BaseModel):
    project_id: UUID
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
    published_at: datetime | None
    created_at: datetime
    updated_at: datetime


class KnowledgeBaseListResponse(PageResponse):
    items: list[KnowledgeBaseResponse]


class ProjectKnowledgeBaseCreate(BaseModel):
    project_id: UUID


class ProjectKnowledgeBaseResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    project_id: UUID
    knowledge_base_id: UUID
    created_at: datetime


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
    error_code: str | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime


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


class DocumentUploadResponse(BaseModel):
    document: DocumentResponse
    version: DocumentVersionResponse
    ingestion_job: IngestionJobResponse
