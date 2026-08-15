"""Tenant-scoped persistence operations for long-term user memory."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import cast
from uuid import UUID

from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.identity import (
    MemoryCategory,
    MemoryEmbeddingStatus,
    MemoryStatus,
    UserMemory,
    UserMemoryConfirmation,
    UserMemorySettings,
)


class MemoryRepository:
    """所有记忆查询显式携带用户归属谓词，并由 RLS 再次约束。"""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_settings(
        self, user_id: UUID, *, for_update: bool = False
    ) -> UserMemorySettings | None:
        statement = select(UserMemorySettings).where(UserMemorySettings.user_id == user_id)
        if for_update:
            statement = statement.with_for_update()
        return cast(UserMemorySettings | None, await self._session.scalar(statement))

    async def get_memory(
        self, user_id: UUID, memory_id: UUID, *, for_update: bool = False
    ) -> UserMemory | None:
        statement = select(UserMemory).where(
            UserMemory.id == memory_id,
            UserMemory.user_id == user_id,
        )
        if for_update:
            statement = statement.with_for_update()
        return cast(UserMemory | None, await self._session.scalar(statement))

    async def get_by_idempotency_key(
        self, user_id: UUID, idempotency_key: str
    ) -> UserMemory | None:
        statement = select(UserMemory).where(
            UserMemory.user_id == user_id,
            UserMemory.create_idempotency_key == idempotency_key,
        )
        return cast(UserMemory | None, await self._session.scalar(statement))

    async def get_by_source_ordinal(
        self, user_id: UUID, source_message_id: UUID, source_ordinal: int
    ) -> UserMemory | None:
        statement = select(UserMemory).where(
            UserMemory.user_id == user_id,
            UserMemory.source_message_id == source_message_id,
            UserMemory.source_ordinal == source_ordinal,
        )
        return cast(UserMemory | None, await self._session.scalar(statement))

    async def get_active_by_content_hash(
        self, user_id: UUID, content_hash: str
    ) -> UserMemory | None:
        statement = select(UserMemory).where(
            UserMemory.user_id == user_id,
            UserMemory.content_hash == content_hash,
            UserMemory.status == MemoryStatus.ACTIVE,
        )
        return cast(UserMemory | None, await self._session.scalar(statement))

    async def count_for_user(self, user_id: UUID) -> int:
        return int(
            await self._session.scalar(
                select(func.count()).select_from(UserMemory).where(UserMemory.user_id == user_id)
            )
            or 0
        )

    async def list_memories(
        self,
        user_id: UUID,
        *,
        category: MemoryCategory | None,
        status: MemoryStatus | None,
        search: str | None,
        page: int,
        page_size: int,
    ) -> tuple[list[UserMemory], int]:
        filters = [UserMemory.user_id == user_id]
        if category is not None:
            filters.append(UserMemory.category == category)
        if status is not None:
            filters.append(UserMemory.status == status)
        if search:
            pattern = f"%{search.strip()}%"
            filters.append(
                or_(UserMemory.title.ilike(pattern), UserMemory.content.ilike(pattern))
            )
        total = int(
            await self._session.scalar(
                select(func.count()).select_from(UserMemory).where(*filters)
            )
            or 0
        )
        statement = (
            select(UserMemory)
            .where(*filters)
            .order_by(UserMemory.updated_at.desc(), UserMemory.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list((await self._session.scalars(statement)).all()), total

    async def list_embedding_candidates(
        self,
        user_id: UUID,
        *,
        embedding_model: str,
        limit: int,
    ) -> list[UserMemory]:
        statement = (
            select(UserMemory)
            .where(
                UserMemory.user_id == user_id,
                UserMemory.status == MemoryStatus.ACTIVE,
                or_(
                    UserMemory.embedding.is_(None),
                    UserMemory.embedding_model != embedding_model,
                    UserMemory.embedding_model.is_(None),
                    UserMemory.embedding_status != MemoryEmbeddingStatus.READY,
                ),
            )
            .order_by(UserMemory.updated_at, UserMemory.id)
            .limit(limit)
        )
        return list((await self._session.scalars(statement)).all())

    async def set_embedding_result(
        self,
        *,
        user_id: UUID,
        memory_id: UUID,
        embedding: Sequence[float] | None,
        embedding_model: str | None,
        status: MemoryEmbeddingStatus,
    ) -> None:
        # Embedding 生命周期不是用户内容编辑，不能污染用于排序和审计的 updated_at。
        await self._session.execute(
            update(UserMemory)
            .where(UserMemory.user_id == user_id, UserMemory.id == memory_id)
            .values(
                embedding=list(embedding) if embedding is not None else None,
                embedding_model=embedding_model,
                embedding_status=status,
                updated_at=UserMemory.updated_at,
            )
            .execution_options(synchronize_session=False)
        )

    async def search_by_vector(
        self,
        user_id: UUID,
        *,
        vector: Sequence[float],
        embedding_model: str,
        category: MemoryCategory | None,
        limit: int,
    ) -> list[tuple[UserMemory, float]]:
        filters = [
            UserMemory.user_id == user_id,
            UserMemory.status == MemoryStatus.ACTIVE,
            UserMemory.embedding.is_not(None),
            UserMemory.embedding_model == embedding_model,
            UserMemory.embedding_status == MemoryEmbeddingStatus.READY,
        ]
        if category is not None:
            filters.append(UserMemory.category == category)
        distance = UserMemory.embedding.cosine_distance(list(vector)).label("distance")
        statement = (
            select(UserMemory, distance)
            .where(*filters)
            .order_by(distance, UserMemory.updated_at.desc(), UserMemory.id)
            .limit(limit)
        )
        rows = (await self._session.execute(statement)).all()
        return [
            (memory, max(-1.0, min(1.0, 1.0 - float(distance_value))))
            for memory, distance_value in rows
        ]

    async def search_by_text(
        self,
        user_id: UUID,
        *,
        query: str,
        category: MemoryCategory | None,
        limit: int,
    ) -> list[tuple[UserMemory, float]]:
        normalized_query = query.strip()
        if not normalized_query:
            return []
        filters = [
            UserMemory.user_id == user_id,
            UserMemory.status == MemoryStatus.ACTIVE,
        ]
        if category is not None:
            filters.append(UserMemory.category == category)
        similarity = func.greatest(
            func.word_similarity(normalized_query, UserMemory.title),
            func.word_similarity(normalized_query, UserMemory.content),
        ).label("similarity")
        statement = (
            select(UserMemory, similarity)
            .where(*filters, similarity > 0)
            .order_by(similarity.desc(), UserMemory.updated_at.desc(), UserMemory.id)
            .limit(limit)
        )
        rows = (await self._session.execute(statement)).all()
        return [
            (memory, max(0.0, min(1.0, float(score))))
            for memory, score in rows
        ]

    async def record_usage(
        self,
        user_id: UUID,
        *,
        memory_ids: Sequence[UUID],
        used_at: datetime,
    ) -> None:
        if not memory_ids:
            return
        await self._session.execute(
            update(UserMemory)
            .where(
                UserMemory.user_id == user_id,
                UserMemory.id.in_(memory_ids),
            )
            .values(
                use_count=UserMemory.use_count + 1,
                last_used_at=used_at,
                updated_at=UserMemory.updated_at,
            )
            .execution_options(synchronize_session=False)
        )

    async def add_settings(self, settings: UserMemorySettings) -> UserMemorySettings:
        self._session.add(settings)
        await self._session.flush()
        return settings

    async def add_memory(self, memory: UserMemory) -> UserMemory:
        self._session.add(memory)
        await self._session.flush()
        return memory

    async def get_confirmation(
        self, user_id: UUID, confirmation_id: UUID, *, for_update: bool = False
    ) -> UserMemoryConfirmation | None:
        statement = select(UserMemoryConfirmation).where(
            UserMemoryConfirmation.id == confirmation_id,
            UserMemoryConfirmation.user_id == user_id,
        )
        if for_update:
            statement = statement.with_for_update()
        return cast(UserMemoryConfirmation | None, await self._session.scalar(statement))

    async def get_confirmation_for_message(
        self, user_id: UUID, source_message_id: UUID
    ) -> UserMemoryConfirmation | None:
        statement = select(UserMemoryConfirmation).where(
            UserMemoryConfirmation.user_id == user_id,
            UserMemoryConfirmation.source_message_id == source_message_id,
        )
        return cast(UserMemoryConfirmation | None, await self._session.scalar(statement))

    async def add_confirmation(
        self, confirmation: UserMemoryConfirmation
    ) -> UserMemoryConfirmation:
        self._session.add(confirmation)
        await self._session.flush()
        return confirmation

    async def delete_memory(self, memory: UserMemory) -> None:
        await self._session.delete(memory)
        await self._session.flush()
