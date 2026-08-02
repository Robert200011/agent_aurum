"""SQLAlchemy persistence operations for administrator-managed RAG resources."""

from __future__ import annotations

from datetime import datetime
from typing import TypeVar, cast
from uuid import UUID

from sqlalchemy import exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.rag import (
    AgentProject,
    Document,
    DocumentChunk,
    DocumentUploadRequest,
    DocumentVersion,
    IngestionJob,
    KnowledgeBase,
    OutboxEvent,
    ProjectKnowledgeBase,
)

T = TypeVar("T")


class RagRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, instance: T) -> T:
        self._session.add(instance)
        await self._session.flush()
        return instance

    async def get_project(
        self,
        project_id: UUID,
        *,
        include_deleted: bool = False,
        for_update: bool = False,
    ) -> AgentProject | None:
        filters = [AgentProject.id == project_id]
        if not include_deleted:
            filters.append(AgentProject.deleted_at.is_(None))
        statement = select(AgentProject).where(*filters)
        if for_update:
            statement = statement.with_for_update()
        return cast(AgentProject | None, await self._session.scalar(statement))

    async def list_projects(self, *, page: int, page_size: int) -> tuple[list[AgentProject], int]:
        filters = [AgentProject.deleted_at.is_(None)]
        count_statement = select(func.count()).select_from(AgentProject).where(*filters)
        total = int(await self._session.scalar(count_statement) or 0)
        statement = (
            select(AgentProject)
            .where(*filters)
            .order_by(AgentProject.created_at.desc(), AgentProject.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list((await self._session.scalars(statement)).all()), total

    async def list_available_chat_projects(self) -> list[AgentProject]:
        """返回至少包含一个可执行 Dense 检索 Chunk 的正常项目。"""

        published_knowledge_base = exists().where(
            ProjectKnowledgeBase.project_id == AgentProject.id,
            ProjectKnowledgeBase.knowledge_base_id == KnowledgeBase.id,
            KnowledgeBase.status == "published",
            KnowledgeBase.deleted_at.is_(None),
            Document.knowledge_base_id == KnowledgeBase.id,
            Document.status == "published",
            Document.is_enabled.is_(True),
            Document.deleted_at.is_(None),
            Document.current_published_version_id == DocumentVersion.id,
            DocumentVersion.status == "published",
            DocumentChunk.document_version_id == DocumentVersion.id,
            DocumentChunk.embedding.is_not(None),
        )
        statement = (
            select(AgentProject)
            .where(
                AgentProject.status == "active",
                AgentProject.deleted_at.is_(None),
                published_knowledge_base,
            )
            .order_by(AgentProject.name, AgentProject.id)
        )
        return list((await self._session.scalars(statement)).all())

    async def get_knowledge_base(
        self,
        knowledge_base_id: UUID,
        *,
        include_deleted: bool = False,
        for_update: bool = False,
    ) -> KnowledgeBase | None:
        filters = [KnowledgeBase.id == knowledge_base_id]
        if not include_deleted:
            filters.append(KnowledgeBase.deleted_at.is_(None))
        statement = select(KnowledgeBase).where(*filters)
        if for_update:
            statement = statement.with_for_update()
        return cast(KnowledgeBase | None, await self._session.scalar(statement))

    async def list_knowledge_bases(
        self,
        *,
        page: int,
        page_size: int,
    ) -> tuple[list[KnowledgeBase], int]:
        filters = [KnowledgeBase.deleted_at.is_(None)]
        count_statement = select(func.count()).select_from(KnowledgeBase).where(*filters)
        total = int(await self._session.scalar(count_statement) or 0)
        statement = (
            select(KnowledgeBase)
            .where(*filters)
            .order_by(KnowledgeBase.created_at.desc(), KnowledgeBase.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list((await self._session.scalars(statement)).all()), total

    async def get_binding(
        self,
        *,
        project_id: UUID,
        knowledge_base_id: UUID,
    ) -> ProjectKnowledgeBase | None:
        statement = select(ProjectKnowledgeBase).where(
            ProjectKnowledgeBase.project_id == project_id,
            ProjectKnowledgeBase.knowledge_base_id == knowledge_base_id,
        )
        return cast(ProjectKnowledgeBase | None, await self._session.scalar(statement))

    async def list_bindings(self, *, knowledge_base_id: UUID) -> list[ProjectKnowledgeBase]:
        statement = (
            select(ProjectKnowledgeBase)
            .where(ProjectKnowledgeBase.knowledge_base_id == knowledge_base_id)
            .order_by(ProjectKnowledgeBase.created_at, ProjectKnowledgeBase.project_id)
        )
        return list((await self._session.scalars(statement)).all())

    async def has_active_binding(
        self,
        *,
        knowledge_base_id: UUID,
        exclude_project_id: UUID | None = None,
    ) -> bool:
        filters = [
            ProjectKnowledgeBase.knowledge_base_id == knowledge_base_id,
            AgentProject.status == "active",
            AgentProject.deleted_at.is_(None),
        ]
        if exclude_project_id is not None:
            filters.append(ProjectKnowledgeBase.project_id != exclude_project_id)
        statement = select(
            exists().where(
                ProjectKnowledgeBase.project_id == AgentProject.id,
                *filters,
            )
        )
        return bool(await self._session.scalar(statement))

    async def list_bound_knowledge_bases_for_update(
        self,
        *,
        project_id: UUID,
    ) -> list[KnowledgeBase]:
        statement = (
            select(KnowledgeBase)
            .join(
                ProjectKnowledgeBase,
                ProjectKnowledgeBase.knowledge_base_id == KnowledgeBase.id,
            )
            .where(
                ProjectKnowledgeBase.project_id == project_id,
                KnowledgeBase.deleted_at.is_(None),
            )
            .order_by(KnowledgeBase.id)
            .with_for_update()
        )
        return list((await self._session.scalars(statement)).all())

    async def list_published_knowledge_bases_for_project(
        self,
        *,
        project_id: UUID,
    ) -> list[KnowledgeBase]:
        """Return only searchable knowledge bases in one exact active project."""

        statement = (
            select(KnowledgeBase)
            .join(
                ProjectKnowledgeBase,
                ProjectKnowledgeBase.knowledge_base_id == KnowledgeBase.id,
            )
            .join(
                AgentProject,
                AgentProject.id == ProjectKnowledgeBase.project_id,
            )
            .where(
                ProjectKnowledgeBase.project_id == project_id,
                AgentProject.status == "active",
                AgentProject.deleted_at.is_(None),
                KnowledgeBase.status == "published",
                KnowledgeBase.deleted_at.is_(None),
            )
            .order_by(KnowledgeBase.id)
        )
        return list((await self._session.scalars(statement)).all())

    async def delete(self, instance: object) -> None:
        await self._session.delete(instance)
        await self._session.flush()

    async def get_document(
        self,
        document_id: UUID,
        *,
        include_deleted: bool = False,
        for_update: bool = False,
    ) -> Document | None:
        filters = [Document.id == document_id]
        if not include_deleted:
            filters.append(Document.deleted_at.is_(None))
        statement = select(Document).where(*filters)
        if for_update:
            statement = statement.with_for_update()
        return cast(Document | None, await self._session.scalar(statement))

    async def list_documents(
        self, *, knowledge_base_id: UUID, page: int, page_size: int
    ) -> tuple[list[Document], int]:
        filters = [Document.knowledge_base_id == knowledge_base_id, Document.deleted_at.is_(None)]
        count_statement = select(func.count()).select_from(Document).where(*filters)
        total = int(await self._session.scalar(count_statement) or 0)
        statement = (
            select(Document)
            .where(*filters)
            .order_by(Document.created_at.desc(), Document.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list((await self._session.scalars(statement)).all()), total

    async def get_document_version(
        self,
        document_version_id: UUID,
        *,
        for_update: bool = False,
    ) -> DocumentVersion | None:
        statement = select(DocumentVersion).where(DocumentVersion.id == document_version_id)
        if for_update:
            statement = statement.with_for_update()
        return cast(DocumentVersion | None, await self._session.scalar(statement))

    async def list_document_versions(self, *, document_id: UUID) -> list[DocumentVersion]:
        statement = (
            select(DocumentVersion)
            .where(DocumentVersion.document_id == document_id)
            .order_by(DocumentVersion.version.desc())
        )
        return list((await self._session.scalars(statement)).all())

    async def get_version_by_hash(
        self, *, document_id: UUID, content_hash: str
    ) -> DocumentVersion | None:
        statement = select(DocumentVersion).where(
            DocumentVersion.document_id == document_id,
            DocumentVersion.content_hash == content_hash,
        )
        return cast(DocumentVersion | None, await self._session.scalar(statement))

    async def get_job_by_idempotency_key(self, idempotency_key: str) -> IngestionJob | None:
        statement = select(IngestionJob).where(IngestionJob.idempotency_key == idempotency_key)
        return cast(IngestionJob | None, await self._session.scalar(statement))

    async def get_upload_request(
        self,
        idempotency_key: str,
        *,
        for_update: bool = False,
    ) -> DocumentUploadRequest | None:
        statement = select(DocumentUploadRequest).where(
            DocumentUploadRequest.idempotency_key == idempotency_key
        )
        if for_update:
            statement = statement.with_for_update().execution_options(populate_existing=True)
        return cast(DocumentUploadRequest | None, await self._session.scalar(statement))

    async def get_ingestion_job(
        self,
        job_id: UUID,
        *,
        for_update: bool = False,
    ) -> IngestionJob | None:
        statement = select(IngestionJob).where(IngestionJob.id == job_id)
        if for_update:
            statement = statement.with_for_update().execution_options(populate_existing=True)
        return cast(IngestionJob | None, await self._session.scalar(statement))

    async def list_ingestion_jobs(self, *, document_id: UUID) -> list[IngestionJob]:
        statement = (
            select(IngestionJob)
            .where(IngestionJob.document_id == document_id)
            .order_by(IngestionJob.created_at.desc(), IngestionJob.id)
        )
        return list((await self._session.scalars(statement)).all())

    async def get_retrieval_chunks(
        self,
        chunk_ids: list[UUID],
        *,
        project_id: UUID | None = None,
    ) -> dict[UUID, tuple[DocumentChunk, Document, DocumentVersion]]:
        if not chunk_ids:
            return {}
        statement = (
            select(DocumentChunk, Document, DocumentVersion)
            .join(
                DocumentVersion,
                DocumentVersion.id == DocumentChunk.document_version_id,
            )
            .join(Document, Document.id == DocumentVersion.document_id)
            .join(
                KnowledgeBase,
                KnowledgeBase.id == DocumentChunk.knowledge_base_id,
            )
            .where(
                DocumentChunk.id.in_(chunk_ids),
                KnowledgeBase.status == "published",
                KnowledgeBase.deleted_at.is_(None),
                DocumentVersion.status == "published",
                Document.current_published_version_id == DocumentVersion.id,
                Document.is_enabled.is_(True),
                Document.deleted_at.is_(None),
            )
        )
        if project_id is not None:
            statement = statement.where(
                exists().where(
                    ProjectKnowledgeBase.knowledge_base_id
                    == DocumentChunk.knowledge_base_id,
                    ProjectKnowledgeBase.project_id == project_id,
                    AgentProject.id == ProjectKnowledgeBase.project_id,
                    AgentProject.status == "active",
                    AgentProject.deleted_at.is_(None),
                )
            )
        rows = (await self._session.execute(statement)).all()
        return {
            chunk.id: (chunk, document, document_version)
            for chunk, document, document_version in rows
        }

    async def get_outbox_event(
        self, *, ingestion_job_id: UUID, event_type: str
    ) -> OutboxEvent | None:
        statement = select(OutboxEvent).where(
            OutboxEvent.ingestion_job_id == ingestion_job_id,
            OutboxEvent.event_type == event_type,
        )
        return cast(OutboxEvent | None, await self._session.scalar(statement))

    async def get_outbox_event_by_id(
        self,
        event_id: UUID,
        *,
        for_update: bool = False,
    ) -> OutboxEvent | None:
        statement = select(OutboxEvent).where(OutboxEvent.id == event_id)
        if for_update:
            statement = statement.with_for_update().execution_options(populate_existing=True)
        return cast(OutboxEvent | None, await self._session.scalar(statement))

    async def claim_outbox_events(
        self, *, now: datetime, lease_expires_at: datetime, lease_owner: str, limit: int
    ) -> list[OutboxEvent]:
        statement = (
            select(OutboxEvent)
            .where(
                OutboxEvent.status == "pending",
                OutboxEvent.published_at.is_(None),
                OutboxEvent.attempt_count < OutboxEvent.max_attempts,
                (OutboxEvent.lease_expires_at.is_(None) | (OutboxEvent.lease_expires_at <= now)),
                OutboxEvent.available_at <= now,
            )
            .order_by(OutboxEvent.available_at, OutboxEvent.id)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        events = list((await self._session.scalars(statement)).all())
        for event in events:
            event.lease_owner = lease_owner
            event.lease_expires_at = lease_expires_at
            event.attempt_count += 1
        await self._session.flush()
        return events

    async def fail_exhausted_outbox_events(self, *, now: datetime) -> int:
        statement = (
            select(OutboxEvent)
            .where(
                OutboxEvent.status == "pending",
                OutboxEvent.published_at.is_(None),
                OutboxEvent.attempt_count >= OutboxEvent.max_attempts,
                (
                    OutboxEvent.lease_expires_at.is_(None)
                    | (OutboxEvent.lease_expires_at <= now)
                ),
            )
            .with_for_update(skip_locked=True)
        )
        events = list((await self._session.scalars(statement)).all())
        for event in events:
            event.status = "failed"
            event.failed_at = now
            event.last_error = event.last_error or "dispatch attempts exhausted after lease expiry"
            event.lease_owner = None
            event.lease_expires_at = None
        await self._session.flush()
        return len(events)

    async def get_outbox_dispatch_metrics(self) -> tuple[int, int, datetime | None]:
        """Return pending/failed totals and the oldest pending event timestamp."""

        statement = select(
            func.count().filter(OutboxEvent.status == "pending"),
            func.count().filter(OutboxEvent.status == "failed"),
            func.min(OutboxEvent.created_at).filter(OutboxEvent.status == "pending"),
        )
        pending_count, failed_count, oldest_pending_at = (
            await self._session.execute(statement)
        ).one()
        return (
            int(pending_count),
            int(failed_count),
            cast(datetime | None, oldest_pending_at),
        )
