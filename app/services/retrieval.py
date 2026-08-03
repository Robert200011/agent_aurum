"""Dense knowledge-base retrieval with source reconstruction and durable logging."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Sequence
from dataclasses import dataclass, replace
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
from app.observability.metrics import observe_retrieval
from app.providers.model_provider import (
    QueryEmbeddingProvider,
    RerankerProvider,
    RerankerProviderError,
)
from app.providers.pgtrigram_store import PgTrigramStoreProvider
from app.providers.pgvector_store import PgVectorStoreProvider
from app.providers.retrieval_cache import (
    CachedRetrievalItem,
    RedisRetrievalCache,
    RetrievalCacheEntry,
)
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
        reranker_provider: RerankerProvider | None = None,
        hybrid_candidate_multiplier: int = 4,
        rrf_k: int = 60,
        cache: RedisRetrievalCache | None = None,
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
        self._reranker_provider = reranker_provider
        self._hybrid_candidate_multiplier = hybrid_candidate_multiplier
        self._rrf_k = rrf_k
        self._cache = cache

    @observe_retrieval("knowledge_base")
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

    @observe_retrieval("project")
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

        knowledge_base_ids = tuple(knowledge_base.id for knowledge_base in knowledge_bases)
        candidate_limit = limit * self._hybrid_candidate_multiplier
        cache_digest = (
            await self._project_cache_digest(
                project_id=project.id,
                knowledge_bases=knowledge_bases,
                query=query,
                limit=limit,
                min_score=min_score,
            )
            if self._cache is not None
            else ""
        )
        cache_entry = await self._cache.get(cache_digest) if self._cache is not None else None
        cached_items = await self._validated_cached_items(
            entry=cache_entry,
            project_id=project.id,
        )
        cache_hit = cached_items is not None
        dense_hits: Sequence[VectorSearchResult] = ()
        sparse_hits: Sequence[Any] = ()
        candidates: list[RetrievedChunk] = []
        if cache_hit:
            items = cached_items or []
            reranker_applied = cache_entry.reranker_applied if cache_entry is not None else False
            reranker_fallback_code = (
                cache_entry.reranker_fallback_code if cache_entry is not None else None
            )
        else:
            fill_owner = (
                await self._cache.acquire_fill(cache_digest)
                if self._cache is not None
                else None
            )
            if self._cache is not None and fill_owner is None:
                waited = await self._cache.wait_for_fill(cache_digest)
                cached_items = await self._validated_cached_items(
                    entry=waited,
                    project_id=project.id,
                )
                if cached_items is not None:
                    cache_hit = True
                    cache_entry = waited
                    items = cached_items
                    reranker_applied = waited.reranker_applied if waited is not None else False
                    reranker_fallback_code = (
                        waited.reranker_fallback_code if waited is not None else None
                    )
            if not cache_hit:
                try:
                    query_vector = await self._embed_query(query)
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
                    fused_hits = reciprocal_rank_fuse(
                        dense_hits=dense_hits,
                        sparse_hits=sparse_hits,
                        limit=candidate_limit,
                        rrf_k=self._rrf_k,
                    )
                    persisted = await self._repository.get_retrieval_chunks(
                        [hit.chunk_id for hit in fused_hits],
                        project_id=project.id,
                    )
                    candidates = self._reconstruct_items(
                        hits=fused_hits,
                        persisted=persisted,
                        min_score=None,
                    )
                    items, reranker_applied, reranker_fallback_code = (
                        await self._rerank_candidates(
                            query=query,
                            candidates=candidates,
                            limit=limit,
                            min_score=min_score,
                        )
                    )
                    if self._cache is not None:
                        await self._cache.set(
                            cache_digest,
                            RetrievalCacheEntry(
                                items=tuple(
                                    CachedRetrievalItem(
                                        chunk_id=item.chunk_id,
                                        document_version_id=item.document_version_id,
                                        knowledge_base_id=item.knowledge_base_id,
                                        score=item.score,
                                        retrieval_source=item.retrieval_source,
                                    )
                                    for item in items
                                ),
                                reranker_applied=reranker_applied,
                                reranker_fallback_code=reranker_fallback_code,
                            ),
                        )
                finally:
                    if self._cache is not None and fill_owner is not None:
                        await self._cache.release_fill(cache_digest, fill_owner)

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
                        "retrieval_source": (
                            "cache"
                            if cache_hit
                            else "hybrid_rerank"
                            if reranker_applied
                            else "hybrid"
                        ),
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
                        "fusion_candidate_count": len(candidates),
                        "rrf_k": self._rrf_k,
                        "reranker_applied": reranker_applied,
                        "reranker_provider": (
                            self._reranker_provider.provider_name
                            if self._reranker_provider is not None
                            else None
                        ),
                        "reranker_model": (
                            self._reranker_provider.model_name
                            if self._reranker_provider is not None
                            else None
                        ),
                        "reranker_fallback_code": reranker_fallback_code,
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

    async def _project_cache_digest(
        self,
        *,
        project_id: UUID,
        knowledge_bases: Sequence[KnowledgeBase],
        query: str,
        limit: int,
        min_score: float | None,
    ) -> str:
        document_state = await self._repository.get_project_retrieval_version_state(
            project_id=project_id,
            knowledge_base_ids=[item.id for item in knowledge_bases],
        )
        scope = {
            "schema": 1,
            "actor": hashlib.sha256(self._actor_user_id.bytes).hexdigest(),
            "project": str(project_id),
            "knowledge_bases": [
                (
                    str(item.id),
                    item.published_at.isoformat() if item.published_at is not None else None,
                    item.pipeline_version,
                    item.embedding_provider,
                    item.embedding_model,
                    item.embedding_dimensions,
                )
                for item in knowledge_bases
            ],
            "documents": [tuple(str(value) for value in row) for row in document_state],
            "query_hash": hashlib.sha256(query.casefold().encode("utf-8")).hexdigest(),
            "embedding": (
                self._embedding_provider.provider_name,
                self._embedding_provider.model_name,
                self._embedding_provider.dimensions,
            ),
            "reranker": (
                self._reranker_provider.provider_name,
                self._reranker_provider.model_name,
            )
            if self._reranker_provider is not None
            else None,
            "parameters": (
                limit,
                min_score,
                self._hybrid_candidate_multiplier,
                self._rrf_k,
            ),
        }
        serialized = json.dumps(scope, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    async def _validated_cached_items(
        self,
        *,
        entry: RetrievalCacheEntry | None,
        project_id: UUID,
    ) -> list[RetrievedChunk] | None:
        if entry is None:
            return None
        persisted = await self._repository.get_retrieval_chunks(
            [item.chunk_id for item in entry.items],
            project_id=project_id,
        )
        if len(persisted) != len(entry.items):
            return None
        hits = [
            HybridSearchResult(
                chunk_id=item.chunk_id,
                document_version_id=item.document_version_id,
                knowledge_base_id=item.knowledge_base_id,
                score=item.score,
                retrieval_source=item.retrieval_source,
            )
            for item in entry.items
        ]
        return self._reconstruct_items(hits=hits, persisted=persisted, min_score=None)

    async def _rerank_candidates(
        self,
        *,
        query: str,
        candidates: list[RetrievedChunk],
        limit: int,
        min_score: float | None,
    ) -> tuple[list[RetrievedChunk], bool, str | None]:
        """重排融合候选；Provider 故障时保留确定性的 RRF 结果。"""

        if not candidates:
            return [], False, None
        if self._reranker_provider is None:
            return _filter_and_limit(candidates, limit=limit, min_score=min_score), False, None
        try:
            scores = await self._reranker_provider.rerank(
                query,
                [candidate.content for candidate in candidates],
            )
        except RerankerProviderError as exc:
            return (
                _filter_and_limit(candidates, limit=limit, min_score=min_score),
                False,
                exc.code,
            )
        if (
            len(scores) != len(candidates)
            or any(not math.isfinite(score) or not 0.0 <= score <= 1.0 for score in scores)
        ):
            return (
                _filter_and_limit(candidates, limit=limit, min_score=min_score),
                False,
                "reranker_response_invalid",
            )

        reranked = [
            replace(candidate, score=score)
            for candidate, score in zip(candidates, scores, strict=True)
        ]
        reranked.sort(key=lambda item: item.score, reverse=True)
        return (
            _filter_and_limit(reranked, limit=limit, min_score=min_score),
            True,
            None,
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


def _filter_and_limit(
    items: Sequence[RetrievedChunk],
    *,
    limit: int,
    min_score: float | None,
) -> list[RetrievedChunk]:
    return [
        item
        for item in items
        if min_score is None or item.score >= min_score
    ][:limit]
