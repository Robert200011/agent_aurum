"""Dense knowledge-base retrieval with source reconstruction and durable logging."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from time import perf_counter
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.rag import (
    Document,
    DocumentChunk,
    DocumentVersion,
    KnowledgeBase,
    RetrievalLog,
)
from app.db.repositories.rag import RagRepository
from app.db.session import set_tenant_context
from app.errors import BusinessRuleError, NotFoundError, ServiceUnavailableError
from app.providers.model_provider import QueryEmbeddingProvider
from app.providers.pgtrigram_store import PgTrigramStoreProvider
from app.providers.pgvector_store import PgVectorStoreProvider
from app.providers.sparse_store import SparseStoreProvider
from app.providers.vector_store import VectorSearchResult, VectorStoreProvider
from app.rag.embeddings.dashscope import EmbeddingProviderFailure
from app.rag.retrievers.hybrid import HybridSearchResult, reciprocal_rank_fuse


@dataclass(frozen=True, slots=True)
class RetrievedChunk:
    chunk_id: UUID
    document_id: UUID
    document_version_id: UUID
    document_version: int
    knowledge_base_id: UUID
    content: str
    content_hash: str
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


@dataclass(frozen=True, slots=True)
class RetrievalResult:
    knowledge_base_id: UUID
    query: str
    embedding_model: str
    latency_ms: int
    items: list[RetrievedChunk]


@dataclass(frozen=True, slots=True)
class ProjectRetrievalResult:
    """Top-K Dense results merged across one project's published knowledge bases."""

    project_id: UUID
    knowledge_base_ids: tuple[UUID, ...]
    query: str
    embedding_model: str
    latency_ms: int
    items: list[RetrievedChunk]


class RagRetrievalService:
    """Run scoped Dense retrieval for admin diagnostics and user RAG flows."""

    def __init__(
        self,
        *,
        session: AsyncSession,
        actor_user_id: UUID,
        embedding_provider: QueryEmbeddingProvider,
        vector_store: VectorStoreProvider | None = None,
        sparse_store: SparseStoreProvider | None = None,
        hybrid_candidate_multiplier: int = 4,
        rrf_k: int = 60,
    ) -> None:
        if hybrid_candidate_multiplier < 1:
            raise ValueError("hybrid candidate multiplier must be positive")
        if rrf_k < 1:
            raise ValueError("RRF rank constant must be positive")
        self._session = session
        self._actor_user_id = actor_user_id
        self._embedding_provider = embedding_provider
        self._repository = RagRepository(session)
        self._vector_store = vector_store or PgVectorStoreProvider(session)
        self._sparse_store = sparse_store or PgTrigramStoreProvider(session)
        self._hybrid_candidate_multiplier = hybrid_candidate_multiplier
        self._rrf_k = rrf_k

    async def retrieve(
        self,
        *,
        knowledge_base_id: UUID,
        query: str,
        limit: int,
        min_score: float | None,
    ) -> RetrievalResult:
        query = _validated_query(query, limit=limit, min_score=min_score)

        await set_tenant_context(self._session, self._actor_user_id)
        started = perf_counter()
        knowledge_base = await self._repository.get_knowledge_base(knowledge_base_id)
        if knowledge_base is None:
            raise NotFoundError("knowledge base was not found")
        if knowledge_base.status != "published":
            raise BusinessRuleError("only published knowledge bases can be searched")
        if not await self._repository.has_active_binding(
            knowledge_base_id=knowledge_base.id
        ):
            raise BusinessRuleError("knowledge base has no active project scope")
        if not self._supports_embedding_configuration(knowledge_base):
            raise ServiceUnavailableError(
                "knowledge base query embedding configuration is unavailable"
            )

        query_vector = await self._embed_query(query)
        hits = await self._vector_store.search(
            knowledge_base_ids=[knowledge_base.id],
            vector=query_vector,
            limit=limit,
        )
        persisted = await self._repository.get_retrieval_chunks(
            [hit.chunk_id for hit in hits]
        )
        items = self._reconstruct_items(
            hits=hits,
            persisted=persisted,
            min_score=min_score,
        )

        latency_ms = max(0, round((perf_counter() - started) * 1000))
        self._session.add(
            RetrievalLog(
                user_id=self._actor_user_id,
                knowledge_base_id=knowledge_base.id,
                query=query,
                result_count=len(items),
                latency_ms=latency_ms,
                top_score=items[0].score if items else None,
                detail={
                    "retrieval_source": "dense",
                    "embedding_model": knowledge_base.embedding_model,
                    "requested_limit": limit,
                    "min_score": min_score,
                },
            )
        )
        await self._session.commit()
        return RetrievalResult(
            knowledge_base_id=knowledge_base.id,
            query=query,
            embedding_model=knowledge_base.embedding_model,
            latency_ms=latency_ms,
            items=items,
        )

    async def retrieve_project(
        self,
        *,
        project_id: UUID,
        query: str,
        limit: int,
        min_score: float | None,
    ) -> ProjectRetrievalResult:
        """Search one exact active project without exposing raw chunks as a public API."""

        query = _validated_query(query, limit=limit, min_score=min_score)
        await set_tenant_context(self._session, self._actor_user_id)
        started = perf_counter()
        project = await self._repository.get_project(project_id)
        if project is None:
            raise NotFoundError("project was not found")
        if project.status != "active":
            raise BusinessRuleError("only active projects can be searched")

        knowledge_bases = await self._repository.list_published_knowledge_bases_for_project(
            project_id=project.id
        )
        if not knowledge_bases:
            raise BusinessRuleError("project has no published knowledge bases")
        if any(
            not self._supports_embedding_configuration(knowledge_base)
            for knowledge_base in knowledge_bases
        ):
            raise ServiceUnavailableError(
                "project query embedding configuration is unavailable"
            )

        query_vector = await self._embed_query(query)
        knowledge_base_ids = tuple(knowledge_base.id for knowledge_base in knowledge_bases)
        candidate_limit = limit * self._hybrid_candidate_multiplier
        dense_hits = await self._vector_store.search(
            knowledge_base_ids=knowledge_base_ids,
            vector=query_vector,
            limit=candidate_limit,
            project_id=project.id,
        )
        sparse_hits = await self._sparse_store.search(
            knowledge_base_ids=knowledge_base_ids,
            query=query,
            limit=candidate_limit,
            project_id=project.id,
        )
        hits = reciprocal_rank_fuse(
            dense_hits=dense_hits,
            sparse_hits=sparse_hits,
            limit=limit,
            rrf_k=self._rrf_k,
        )
        persisted = await self._repository.get_retrieval_chunks(
            [hit.chunk_id for hit in hits],
            project_id=project.id,
        )
        items = self._reconstruct_items(
            hits=hits,
            persisted=persisted,
            min_score=min_score,
        )

        latency_ms = max(0, round((perf_counter() - started) * 1000))
        items_by_knowledge_base = {
            knowledge_base_id: [
                item for item in items if item.knowledge_base_id == knowledge_base_id
            ]
            for knowledge_base_id in knowledge_base_ids
        }
        for knowledge_base in knowledge_bases:
            scoped_items = items_by_knowledge_base[knowledge_base.id]
            self._session.add(
                RetrievalLog(
                    user_id=self._actor_user_id,
                    knowledge_base_id=knowledge_base.id,
                    query=query,
                    result_count=len(scoped_items),
                    latency_ms=latency_ms,
                    top_score=scoped_items[0].score if scoped_items else None,
                    detail={
                        "retrieval_source": "hybrid",
                        "scope": "project",
                        "project_id": str(project.id),
                        "embedding_model": knowledge_base.embedding_model,
                        "requested_limit": limit,
                        "candidate_limit": candidate_limit,
                        "min_score": min_score,
                        "dense_candidate_count": sum(
                            hit.knowledge_base_id == knowledge_base.id
                            for hit in dense_hits
                        ),
                        "sparse_candidate_count": sum(
                            hit.knowledge_base_id == knowledge_base.id
                            for hit in sparse_hits
                        ),
                        "rrf_k": self._rrf_k,
                        "total_result_count": len(items),
                        "searched_knowledge_base_count": len(knowledge_bases),
                    },
                )
            )
        await self._session.commit()
        return ProjectRetrievalResult(
            project_id=project.id,
            knowledge_base_ids=knowledge_base_ids,
            query=query,
            embedding_model=self._embedding_provider.model_name,
            latency_ms=latency_ms,
            items=items,
        )

    async def _embed_query(self, query: str) -> list[float]:
        try:
            return await self._embedding_provider.embed_query(query)
        except EmbeddingProviderFailure as exc:
            message = (
                "query embedding is not configured"
                if exc.code == "embedding_configuration_missing"
                else "query embedding provider is unavailable"
            )
            raise ServiceUnavailableError(message) from exc

    def _supports_embedding_configuration(self, knowledge_base: KnowledgeBase) -> bool:
        return (
            self._embedding_provider.provider_name == knowledge_base.embedding_provider
            and self._embedding_provider.model_name == knowledge_base.embedding_model
            and self._embedding_provider.dimensions == knowledge_base.embedding_dimensions
        )

    @staticmethod
    def _reconstruct_items(
        *,
        hits: Sequence[VectorSearchResult | HybridSearchResult],
        persisted: dict[UUID, tuple[DocumentChunk, Document, DocumentVersion]],
        min_score: float | None,
    ) -> list[RetrievedChunk]:
        items: list[RetrievedChunk] = []
        for hit in hits:
            if min_score is not None and hit.score < min_score:
                continue
            source = persisted.get(hit.chunk_id)
            if source is None:
                continue
            chunk, document, document_version = source
            items.append(
                RetrievedChunk(
                    chunk_id=chunk.id,
                    document_id=document.id,
                    document_version_id=chunk.document_version_id,
                    document_version=document_version.version,
                    knowledge_base_id=chunk.knowledge_base_id,
                    content=chunk.content,
                    content_hash=chunk.content_hash,
                    title=document.name,
                    page_number=chunk.page_number,
                    section_path=chunk.section_path,
                    sheet_name=chunk.sheet_name,
                    row_start=chunk.row_start,
                    row_end=chunk.row_end,
                    char_start=chunk.char_start,
                    char_end=chunk.char_end,
                    metadata=dict(chunk.metadata_json),
                    score=hit.score,
                    retrieval_source=(
                        hit.retrieval_source
                        if isinstance(hit, HybridSearchResult)
                        else "dense"
                    ),
                )
            )
        return items


def _validated_query(query: str, *, limit: int, min_score: float | None) -> str:
    normalized = query.strip()
    if not normalized or len(normalized) > 2_000:
        raise BusinessRuleError("retrieval query is not valid")
    if limit < 1 or limit > 50:
        raise BusinessRuleError("retrieval result limit is not valid")
    if min_score is not None and not -1.0 <= min_score <= 1.0:
        raise BusinessRuleError("retrieval score threshold is not valid")
    return normalized
