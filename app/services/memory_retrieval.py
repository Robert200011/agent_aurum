"""当前登录用户的长期记忆向量化、检索和受控上下文服务。"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from time import perf_counter
from typing import Protocol
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.identity import (
    MemoryCategory,
    MemoryEmbeddingStatus,
    PersonalFinancialProfile,
    UserMemory,
)
from app.db.repositories.identity import UserSettingsRepository
from app.db.repositories.memory import MemoryRepository
from app.db.session import set_tenant_context
from app.memory.retrieval import (
    MemoryRetrievalResult,
    RetrievedMemory,
    build_controlled_memory_context,
    empty_memory_retrieval,
)
from app.observability.metrics import (
    MEMORY_EMBEDDINGS,
    MEMORY_RETRIEVAL_DURATION,
    MEMORY_RETRIEVAL_REQUESTS,
    MEMORY_RETRIEVAL_RESULTS,
)
from app.providers.model_provider import EmbeddingProvider, QueryEmbeddingProvider
from app.rag.embeddings.dashscope import EmbeddingProviderFailure


class MemoryEmbeddingProvider(EmbeddingProvider, QueryEmbeddingProvider, Protocol):
    """记忆索引同时需要文档和查询两种 Embedding 能力。"""


class MemoryRetrievalService:
    """懒生成记忆向量，并在 Provider 失败时限量降级为文本相关性检索。"""

    def __init__(
        self,
        *,
        session: AsyncSession,
        actor_user_id: UUID,
        embedding_provider: MemoryEmbeddingProvider,
        retrieval_limit: int,
        context_max_characters: int,
        item_max_characters: int,
        max_items_per_user: int,
        enabled: bool = True,
        embedding_enabled: bool = True,
    ) -> None:
        self._session = session
        self._actor_user_id = actor_user_id
        self._embedding_provider = embedding_provider
        self._retrieval_limit = retrieval_limit
        self._context_max_characters = context_max_characters
        self._item_max_characters = min(item_max_characters, 800)
        self._max_items_per_user = max_items_per_user
        self._enabled = enabled
        self._embedding_enabled = embedding_enabled
        self._repository = MemoryRepository(session)
        self._settings_repository = UserSettingsRepository(session)

    @property
    def actor_user_id(self) -> UUID:
        return self._actor_user_id

    @property
    def enabled(self) -> bool:
        return self._enabled

    async def retrieve(
        self,
        *,
        query: str,
        category: MemoryCategory | None = None,
        limit: int | None = None,
    ) -> MemoryRetrievalResult:
        normalized_query = query.strip()
        effective_limit = min(limit or self._retrieval_limit, self._retrieval_limit)
        if not normalized_query or not self._enabled:
            MEMORY_RETRIEVAL_REQUESTS.labels(mode="disabled", outcome="skipped").inc()
            return empty_memory_retrieval(
                owner_user_id=self._actor_user_id,
                query=normalized_query,
            )

        await set_tenant_context(self._session, self._actor_user_id)
        started = perf_counter()
        settings = await self._repository.get_settings(self._actor_user_id)
        if settings is not None and (
            not settings.memory_enabled or not settings.answer_recall_enabled
        ):
            MEMORY_RETRIEVAL_REQUESTS.labels(mode="disabled", outcome="skipped").inc()
            return empty_memory_retrieval(
                owner_user_id=self._actor_user_id,
                query=normalized_query,
            )

        profile = await self._settings_repository.get_financial_profile(self._actor_user_id)
        profile_snapshot = _financial_profile_snapshot(profile)
        degraded_to_text = not self._embedding_enabled
        hits: list[tuple[UserMemory, float]]
        if self._embedding_enabled:
            try:
                await self._refresh_embeddings()
                query_vector = await self._embedding_provider.embed_query(normalized_query)
                # 懒索引可能已提交独立事务，向量查询前重新建立 transaction-local RLS 上下文。
                await set_tenant_context(self._session, self._actor_user_id)
                hits = await self._repository.search_by_vector(
                    self._actor_user_id,
                    vector=query_vector,
                    embedding_model=self._embedding_provider.model_name,
                    category=category,
                    limit=effective_limit,
                )
            except EmbeddingProviderFailure:
                degraded_to_text = True
                await set_tenant_context(self._session, self._actor_user_id)
                hits = await self._repository.search_by_text(
                    self._actor_user_id,
                    query=normalized_query,
                    category=category,
                    limit=effective_limit,
                )
        else:
            await set_tenant_context(self._session, self._actor_user_id)
            hits = await self._repository.search_by_text(
                self._actor_user_id,
                query=normalized_query,
                category=category,
                limit=effective_limit,
            )

        retrieved = tuple(
            RetrievedMemory(
                memory_id=memory.id,
                category=memory.category,
                title=memory.title,
                content=memory.content,
                content_hash=memory.content_hash,
                updated_at=memory.updated_at,
                score=score,
                retrieval_source="text" if degraded_to_text else "dense",
            )
            for memory, score in hits
        )
        context = build_controlled_memory_context(
            retrieved,
            financial_profile=profile_snapshot,
            max_characters=self._context_max_characters,
            max_item_characters=self._item_max_characters,
        )
        included_ids = set(context.memory_ids)
        included = tuple(item for item in retrieved if item.memory_id in included_ids)
        elapsed = max(0.0, perf_counter() - started)
        mode = "text" if degraded_to_text else "dense"
        MEMORY_RETRIEVAL_REQUESTS.labels(
            mode=mode,
            outcome="hit" if included else "empty",
        ).inc()
        MEMORY_RETRIEVAL_DURATION.labels(mode=mode).observe(elapsed)
        MEMORY_RETRIEVAL_RESULTS.labels(mode=mode).observe(len(included))
        return MemoryRetrievalResult(
            owner_user_id=self._actor_user_id,
            query=normalized_query,
            embedding_model=(
                self._embedding_provider.model_name if not degraded_to_text else ""
            ),
            latency_ms=round(elapsed * 1000),
            items=included,
            financial_profile=profile_snapshot,
            context=context,
            degraded_to_text=degraded_to_text,
        )

    def combine(
        self,
        retrievals: list[MemoryRetrievalResult],
        *,
        query: str,
    ) -> MemoryRetrievalResult:
        """合并同一轮的多次分类检索，并重新应用统一上下文预算。"""

        if not retrievals:
            return empty_memory_retrieval(
                owner_user_id=self._actor_user_id,
                query=query,
            )
        by_id: dict[UUID, RetrievedMemory] = {}
        for retrieval in retrievals:
            for item in retrieval.items:
                previous = by_id.get(item.memory_id)
                if previous is None or item.score > previous.score:
                    by_id[item.memory_id] = item
        items = sorted(
            by_id.values(),
            key=lambda item: (-item.score, -item.updated_at.timestamp(), str(item.memory_id)),
        )[: self._retrieval_limit]
        profile = next(
            (
                retrieval.financial_profile
                for retrieval in reversed(retrievals)
                if retrieval.financial_profile is not None
            ),
            None,
        )
        context = build_controlled_memory_context(
            items,
            financial_profile=profile,
            max_characters=self._context_max_characters,
            max_item_characters=self._item_max_characters,
        )
        included_ids = set(context.memory_ids)
        included = tuple(item for item in items if item.memory_id in included_ids)
        return MemoryRetrievalResult(
            owner_user_id=self._actor_user_id,
            query=query.strip(),
            embedding_model=retrievals[-1].embedding_model,
            latency_ms=sum(retrieval.latency_ms for retrieval in retrievals),
            items=included,
            financial_profile=profile,
            context=context,
            degraded_to_text=any(item.degraded_to_text for item in retrievals),
        )

    async def _refresh_embeddings(self) -> None:
        candidates = await self._repository.list_embedding_candidates(
            self._actor_user_id,
            embedding_model=self._embedding_provider.model_name,
            limit=self._max_items_per_user,
        )
        if not candidates:
            return
        try:
            vectors = await self._embedding_provider.embed(
                [_embedding_text(memory) for memory in candidates]
            )
        except EmbeddingProviderFailure:
            MEMORY_EMBEDDINGS.labels(outcome="error").inc(len(candidates))
            for memory in candidates:
                await self._repository.set_embedding_result(
                    user_id=self._actor_user_id,
                    memory_id=memory.id,
                    embedding=None,
                    embedding_model=None,
                    status=MemoryEmbeddingStatus.FAILED,
                )
            await self._session.commit()
            raise
        for memory, vector in zip(candidates, vectors, strict=True):
            await self._repository.set_embedding_result(
                user_id=self._actor_user_id,
                memory_id=memory.id,
                embedding=vector,
                embedding_model=self._embedding_provider.model_name,
                status=MemoryEmbeddingStatus.READY,
            )
        MEMORY_EMBEDDINGS.labels(outcome="success").inc(len(candidates))
        await self._session.commit()


def _embedding_text(memory: UserMemory) -> str:
    category_value = memory.category.value
    return (
        f"category: {category_value}\n"
        f"title: {memory.title}\n"
        f"content: {memory.content}"
    )


def _financial_profile_snapshot(
    profile: PersonalFinancialProfile | None,
) -> dict[str, str | None] | None:
    if profile is None:
        return None
    return {
        "birth_date": _scalar(profile.birth_date),
        "residence_province": profile.residence_province,
        "residence_city": profile.residence_city,
        "employment_status": (
            profile.employment_status.value if profile.employment_status is not None else None
        ),
        "occupation": profile.occupation,
        "annual_income": _scalar(profile.annual_income),
        "annual_expense_budget": _scalar(profile.annual_expense_budget),
        "currency": profile.currency,
    }


def _scalar(value: date | Decimal | None) -> str | None:
    return str(value) if value is not None else None
