"""Tenant-scoped persistence operations for long-term user memory."""

from __future__ import annotations

from typing import cast
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.identity import (
    MemoryCategory,
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
