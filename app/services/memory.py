"""Long-term memory settings and manual CRUD use cases."""

from __future__ import annotations

import hashlib
import unicodedata
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.identity import (
    MemoryCategory,
    MemoryEmbeddingStatus,
    MemorySourceType,
    MemoryStatus,
    UserMemory,
    UserMemorySettings,
)
from app.db.repositories.identity import AuditRepository
from app.db.repositories.memory import MemoryRepository
from app.db.session import set_tenant_context
from app.errors import BusinessRuleError, ConflictError, NotFoundError


@dataclass(frozen=True, slots=True)
class MemoryPage:
    items: list[UserMemory]
    total: int
    page: int
    page_size: int


def normalized_content_hash(content: str) -> str:
    normalized = " ".join(unicodedata.normalize("NFKC", content).casefold().split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


class MemoryService:
    def __init__(self, *, session: AsyncSession, user_id: UUID, max_items: int = 200) -> None:
        self._session = session
        self._user_id = user_id
        self._max_items = max_items
        self._repository = MemoryRepository(session)
        self._audit = AuditRepository(session)

    async def _prepare(self) -> None:
        await set_tenant_context(self._session, self._user_id)

    async def _commit(self, message: str = "memory was updated concurrently") -> None:
        try:
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            raise ConflictError(message) from exc

    async def get_settings(self) -> UserMemorySettings:
        await self._prepare()
        settings = await self._repository.get_settings(self._user_id)
        if settings is not None:
            return settings
        settings = UserMemorySettings(user_id=self._user_id)
        try:
            await self._repository.add_settings(settings)
            await self._commit("memory settings were created concurrently")
            return settings
        except ConflictError:
            await self._prepare()
            winner = await self._repository.get_settings(self._user_id)
            if winner is None:
                raise
            return winner

    async def update_settings(
        self, *, values: dict[str, bool], fields_set: set[str]
    ) -> UserMemorySettings:
        await self._prepare()
        settings = await self._repository.get_settings(self._user_id, for_update=True)
        if settings is None:
            settings = UserMemorySettings(user_id=self._user_id)
            await self._repository.add_settings(settings)
        changed_fields: set[str] = set()
        for field in fields_set:
            value = values[field]
            if getattr(settings, field) != value:
                setattr(settings, field, value)
                changed_fields.add(field)
        if changed_fields:
            self._audit.add(
                action="identity.user_memory_settings_updated",
                actor_user_id=self._user_id,
                resource_type="user_memory_settings",
                resource_id=str(self._user_id),
                ip=None,
                user_agent=None,
                detail={"changed_fields": sorted(changed_fields)},
            )
        await self._commit()
        return settings

    async def list_memories(
        self,
        *,
        category: MemoryCategory | None,
        status: MemoryStatus | None,
        search: str | None,
        page: int,
        page_size: int,
    ) -> MemoryPage:
        await self._prepare()
        items, total = await self._repository.list_memories(
            self._user_id,
            category=category,
            status=status,
            search=search,
            page=page,
            page_size=page_size,
        )
        return MemoryPage(items=items, total=total, page=page, page_size=page_size)

    async def create_memory(
        self,
        *,
        category: MemoryCategory,
        title: str,
        content: str,
        idempotency_key: str,
    ) -> UserMemory:
        await self._prepare()
        replay = await self._repository.get_by_idempotency_key(self._user_id, idempotency_key)
        if replay is not None:
            if replay.category == category and replay.title == title and replay.content == content:
                return replay
            raise ConflictError("idempotency key was already used for another memory")
        content_hash = normalized_content_hash(content)
        duplicate = await self._repository.get_active_by_content_hash(self._user_id, content_hash)
        if duplicate is not None:
            return duplicate
        if await self._repository.count_for_user(self._user_id) >= self._max_items:
            raise BusinessRuleError("memory item limit has been reached")
        memory = UserMemory(
            user_id=self._user_id,
            category=category,
            title=title,
            content=content,
            status=MemoryStatus.ACTIVE,
            source_type=MemorySourceType.MANUAL_UI,
            create_idempotency_key=idempotency_key,
            content_hash=content_hash,
            embedding_status=MemoryEmbeddingStatus.PENDING,
        )
        try:
            await self._repository.add_memory(memory)
        except IntegrityError as exc:
            await self._session.rollback()
            await self._prepare()
            winner = await self._repository.get_by_idempotency_key(
                self._user_id, idempotency_key
            ) or await self._repository.get_active_by_content_hash(self._user_id, content_hash)
            if winner is not None:
                return winner
            raise ConflictError("memory was created concurrently") from exc
        self._audit_change("identity.user_memory_created", memory, {"category", "title", "content"})
        await self._commit()
        return memory

    async def get_memory(self, memory_id: UUID) -> UserMemory:
        await self._prepare()
        memory = await self._repository.get_memory(self._user_id, memory_id)
        if memory is None:
            raise NotFoundError("memory was not found")
        return memory

    async def update_memory(
        self, memory_id: UUID, *, values: dict[str, Any], fields_set: set[str]
    ) -> UserMemory:
        await self._prepare()
        memory = await self._repository.get_memory(self._user_id, memory_id, for_update=True)
        if memory is None:
            raise NotFoundError("memory was not found")
        changed_fields: set[str] = set()
        for field in fields_set:
            value = values[field]
            if getattr(memory, field) != value:
                setattr(memory, field, value)
                changed_fields.add(field)
        if "content" in changed_fields:
            memory.content_hash = normalized_content_hash(memory.content)
            memory.embedding = None
            memory.embedding_model = None
            memory.embedding_status = MemoryEmbeddingStatus.PENDING
        if changed_fields:
            self._audit_change("identity.user_memory_updated", memory, changed_fields)
        await self._commit("memory conflicts with an existing active memory")
        return memory

    async def delete_memory(self, memory_id: UUID) -> None:
        await self._prepare()
        memory = await self._repository.get_memory(self._user_id, memory_id, for_update=True)
        if memory is None:
            raise NotFoundError("memory was not found")
        self._audit_change("identity.user_memory_deleted", memory, set())
        await self._repository.delete_memory(memory)
        await self._commit()

    def _audit_change(self, action: str, memory: UserMemory, changed_fields: set[str]) -> None:
        self._audit.add(
            action=action,
            actor_user_id=self._user_id,
            resource_type="user_memories",
            resource_id=str(memory.id),
            ip=None,
            user_agent=None,
            detail={
                "category": memory.category.value,
                "changed_fields": sorted(changed_fields),
            },
        )
