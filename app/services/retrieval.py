"""Dense knowledge-base retrieval with source reconstruction and durable logging."""

from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.rag import RetrievalLog
from app.db.repositories.rag import RagRepository
from app.db.session import set_tenant_context
from app.errors import BusinessRuleError, NotFoundError, ServiceUnavailableError
from app.providers.model_provider import QueryEmbeddingProvider
from app.providers.pgvector_store import PgVectorStoreProvider
from app.rag.embeddings.dashscope import EmbeddingProviderFailure


@dataclass(frozen=True, slots=True)
class RetrievedChunk:
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


@dataclass(frozen=True, slots=True)
class RetrievalResult:
    knowledge_base_id: UUID
    query: str
    embedding_model: str
    latency_ms: int
    items: list[RetrievedChunk]


class RagRetrievalService:
    """Run administrator retrieval tests within one published knowledge base."""

    def __init__(
        self,
        *,
        session: AsyncSession,
        actor_user_id: UUID,
        embedding_provider: QueryEmbeddingProvider,
    ) -> None:
        self._session = session
        self._actor_user_id = actor_user_id
        self._embedding_provider = embedding_provider
        self._repository = RagRepository(session)

    async def retrieve(
        self,
        *,
        knowledge_base_id: UUID,
        query: str,
        limit: int,
        min_score: float | None,
    ) -> RetrievalResult:
        query = query.strip()
        if not query or len(query) > 2_000:
            raise BusinessRuleError("retrieval query is not valid")
        if limit < 1 or limit > 50:
            raise BusinessRuleError("retrieval result limit is not valid")
        if min_score is not None and not -1.0 <= min_score <= 1.0:
            raise BusinessRuleError("retrieval score threshold is not valid")

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
        if (
            self._embedding_provider.provider_name != knowledge_base.embedding_provider
            or self._embedding_provider.model_name != knowledge_base.embedding_model
            or self._embedding_provider.dimensions != knowledge_base.embedding_dimensions
        ):
            raise ServiceUnavailableError(
                "knowledge base query embedding configuration is unavailable"
            )

        try:
            query_vector = await self._embedding_provider.embed_query(query)
        except EmbeddingProviderFailure as exc:
            message = (
                "query embedding is not configured"
                if exc.code == "embedding_configuration_missing"
                else "query embedding provider is unavailable"
            )
            raise ServiceUnavailableError(message) from exc
        hits = await PgVectorStoreProvider(self._session).search(
            knowledge_base_ids=[knowledge_base.id],
            vector=query_vector,
            limit=limit,
        )
        persisted = await self._repository.get_retrieval_chunks(
            [hit.chunk_id for hit in hits]
        )
        items: list[RetrievedChunk] = []
        for hit in hits:
            if min_score is not None and hit.score < min_score:
                continue
            source = persisted.get(hit.chunk_id)
            if source is None:
                continue
            chunk, document = source
            items.append(
                RetrievedChunk(
                    chunk_id=chunk.id,
                    document_id=document.id,
                    document_version_id=chunk.document_version_id,
                    knowledge_base_id=chunk.knowledge_base_id,
                    content=chunk.content,
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
                    retrieval_source="dense",
                )
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
