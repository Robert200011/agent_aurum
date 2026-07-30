"""PostgreSQL trigram keyword retrieval for current published document chunks."""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.rag import (
    AgentProject,
    Document,
    DocumentChunk,
    DocumentVersion,
    KnowledgeBase,
    ProjectKnowledgeBase,
)
from app.providers.sparse_store import SparseSearchResult
from app.rag.constants import DOCUMENT_VERSION_STATUS_PUBLISHED


class PgTrigramStoreProvider:
    """Use indexed word similarity as a Chinese-friendly Sparse retriever."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def search(
        self,
        *,
        knowledge_base_ids: Sequence[UUID],
        query: str,
        limit: int,
        project_id: UUID,
    ) -> list[SparseSearchResult]:
        normalized_query = query.strip()
        if not knowledge_base_ids or not normalized_query or limit <= 0:
            return []

        similarity = func.word_similarity(
            normalized_query,
            DocumentChunk.content,
        ).label("similarity")
        exact_project_scope = exists().where(
            ProjectKnowledgeBase.knowledge_base_id == DocumentChunk.knowledge_base_id,
            ProjectKnowledgeBase.project_id == project_id,
            AgentProject.id == ProjectKnowledgeBase.project_id,
            AgentProject.status == "active",
            AgentProject.deleted_at.is_(None),
        )
        statement = (
            select(DocumentChunk, similarity)
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
                DocumentChunk.knowledge_base_id.in_(knowledge_base_ids),
                KnowledgeBase.status == "published",
                KnowledgeBase.deleted_at.is_(None),
                DocumentVersion.status == DOCUMENT_VERSION_STATUS_PUBLISHED,
                Document.current_published_version_id == DocumentVersion.id,
                Document.is_enabled.is_(True),
                Document.deleted_at.is_(None),
                exact_project_scope,
                # `%>` is the commutator of word similarity and can use gin_trgm_ops.
                DocumentChunk.content.op("%>")(normalized_query),
            )
            .order_by(similarity.desc(), DocumentChunk.id)
            .limit(limit)
        )
        rows = (await self._session.execute(statement)).all()
        return [
            SparseSearchResult(
                chunk_id=chunk.id,
                document_version_id=chunk.document_version_id,
                knowledge_base_id=chunk.knowledge_base_id,
                score=max(0.0, min(1.0, float(raw_similarity))),
            )
            for chunk, raw_similarity in rows
        ]
