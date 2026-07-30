"""SQLAlchemy/pgvector implementation of the scoped vector-store contract."""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import delete, exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.rag import (
    AgentProject,
    Document,
    DocumentChunk,
    DocumentVersion,
    KnowledgeBase,
    ProjectKnowledgeBase,
)
from app.providers.vector_store import VectorChunk, VectorSearchResult
from app.rag.constants import (
    DASHSCOPE_TEXT_EMBEDDING_V4_DIMENSIONS,
    DOCUMENT_VERSION_STATUS_PUBLISHED,
)


class PgVectorStoreProvider:
    """Write vectors transactionally and search only current published versions."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def replace_version_chunks(
        self,
        *,
        document_version_id: UUID,
        chunks: Sequence[VectorChunk],
    ) -> None:
        expected_ids = {chunk.chunk_id for chunk in chunks}
        if len(expected_ids) != len(chunks):
            raise ValueError("vector chunk identifiers must be unique")
        rows = list(
            (
                await self._session.scalars(
                    select(DocumentChunk).where(
                        DocumentChunk.document_version_id == document_version_id
                    )
                )
            ).all()
        )
        by_id = {row.id: row for row in rows}
        if set(by_id) != expected_ids:
            raise ValueError("vector chunks do not match the persisted document version")
        for chunk in chunks:
            if (
                chunk.document_version_id != document_version_id
                or len(chunk.embedding) != DASHSCOPE_TEXT_EMBEDDING_V4_DIMENSIONS
            ):
                raise ValueError("vector chunk scope or dimensions are invalid")
            by_id[chunk.chunk_id].embedding = [float(value) for value in chunk.embedding]
        await self._session.flush()

    async def delete_version_chunks(self, *, document_version_id: UUID) -> None:
        await self._session.execute(
            delete(DocumentChunk).where(
                DocumentChunk.document_version_id == document_version_id
            )
        )
        await self._session.flush()

    async def search(
        self,
        *,
        knowledge_base_ids: Sequence[UUID],
        vector: Sequence[float],
        limit: int,
        project_id: UUID | None = None,
    ) -> list[VectorSearchResult]:
        if not knowledge_base_ids or limit <= 0:
            return []
        if len(vector) != DASHSCOPE_TEXT_EMBEDDING_V4_DIMENSIONS:
            raise ValueError("query vector dimensions are invalid")
        distance = DocumentChunk.embedding.cosine_distance(list(vector)).label("distance")
        active_project_scope = exists().where(
            ProjectKnowledgeBase.knowledge_base_id == DocumentChunk.knowledge_base_id,
            ProjectKnowledgeBase.project_id == AgentProject.id,
            AgentProject.status == "active",
            AgentProject.deleted_at.is_(None),
        )
        if project_id is not None:
            active_project_scope = active_project_scope.where(
                ProjectKnowledgeBase.project_id == project_id,
            )
        statement = (
            select(DocumentChunk, distance)
            .join(
                DocumentVersion,
                DocumentVersion.id == DocumentChunk.document_version_id,
            )
            .join(
                Document,
                Document.id == DocumentVersion.document_id,
            )
            .join(
                KnowledgeBase,
                KnowledgeBase.id == DocumentChunk.knowledge_base_id,
            )
            .where(
                DocumentChunk.knowledge_base_id.in_(knowledge_base_ids),
                DocumentChunk.embedding.is_not(None),
                KnowledgeBase.status == "published",
                KnowledgeBase.deleted_at.is_(None),
                DocumentVersion.status == DOCUMENT_VERSION_STATUS_PUBLISHED,
                Document.current_published_version_id == DocumentVersion.id,
                Document.is_enabled.is_(True),
                Document.deleted_at.is_(None),
                active_project_scope,
            )
            .order_by(distance, DocumentChunk.id)
            .limit(limit)
        )
        rows = (await self._session.execute(statement)).all()
        return [
            VectorSearchResult(
                chunk_id=chunk.id,
                document_version_id=chunk.document_version_id,
                knowledge_base_id=chunk.knowledge_base_id,
                score=1.0 - float(raw_distance),
            )
            for chunk, raw_distance in rows
        ]
