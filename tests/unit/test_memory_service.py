"""长期记忆 CRUD、幂等、租户归属与脱敏审计测试。"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.identity import (
    MemoryCategory,
    MemorySourceType,
    MemoryStatus,
    UserMemory,
    UserMemorySettings,
)
from app.errors import ConflictError, NotFoundError
from app.services.memory import MemoryService, normalized_content_hash


class FakeSession:
    def __init__(self) -> None:
        self.commits = 0

    async def execute(self, *_: object, **__: object) -> object:
        return object()

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        return None


class FakeRepository:
    def __init__(self) -> None:
        self.settings: dict[UUID, UserMemorySettings] = {}
        self.memories: dict[UUID, UserMemory] = {}
        self.requested_user_ids: list[UUID] = []

    async def get_settings(
        self, user_id: UUID, *, for_update: bool = False
    ) -> UserMemorySettings | None:
        del for_update
        self.requested_user_ids.append(user_id)
        return self.settings.get(user_id)

    async def add_settings(self, settings: UserMemorySettings) -> UserMemorySettings:
        self.settings[settings.user_id] = settings
        return settings

    async def get_memory(
        self, user_id: UUID, memory_id: UUID, *, for_update: bool = False
    ) -> UserMemory | None:
        del for_update
        self.requested_user_ids.append(user_id)
        memory = self.memories.get(memory_id)
        return memory if memory and memory.user_id == user_id else None

    async def get_by_idempotency_key(
        self, user_id: UUID, idempotency_key: str
    ) -> UserMemory | None:
        self.requested_user_ids.append(user_id)
        return next(
            (
                memory
                for memory in self.memories.values()
                if memory.user_id == user_id
                and memory.create_idempotency_key == idempotency_key
            ),
            None,
        )

    async def get_active_by_content_hash(
        self, user_id: UUID, content_hash: str
    ) -> UserMemory | None:
        self.requested_user_ids.append(user_id)
        return next(
            (
                memory
                for memory in self.memories.values()
                if memory.user_id == user_id
                and memory.content_hash == content_hash
                and memory.status == MemoryStatus.ACTIVE
            ),
            None,
        )

    async def count_for_user(self, user_id: UUID) -> int:
        self.requested_user_ids.append(user_id)
        return sum(memory.user_id == user_id for memory in self.memories.values())

    async def list_memories(self, user_id: UUID, **_: Any) -> tuple[list[UserMemory], int]:
        self.requested_user_ids.append(user_id)
        items = [memory for memory in self.memories.values() if memory.user_id == user_id]
        return items, len(items)

    async def add_memory(self, memory: UserMemory) -> UserMemory:
        self.memories[memory.id] = memory
        return memory

    async def delete_memory(self, memory: UserMemory) -> None:
        self.memories.pop(memory.id, None)


class FakeAudit:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    def add(self, **event: Any) -> None:
        self.events.append(event)


def service_fixture(
    user_id: UUID,
) -> tuple[MemoryService, FakeRepository, FakeAudit, FakeSession]:
    session = FakeSession()
    service = MemoryService(session=cast(AsyncSession, session), user_id=user_id)
    repository = FakeRepository()
    audit = FakeAudit()
    service._repository = repository  # type: ignore[assignment]
    service._audit = audit  # type: ignore[assignment]
    return service, repository, audit, session


@pytest.mark.asyncio
async def test_memory_crud_is_user_scoped_and_audit_omits_content() -> None:
    user_id = uuid4()
    service, repository, audit, session = service_fixture(user_id)
    created = await service.create_memory(
        category=MemoryCategory.GOAL,
        title="应急储备",
        content="先建立六个月应急储备",
        idempotency_key="request-1",
    )
    fetched = await service.get_memory(created.id)
    updated = await service.update_memory(
        created.id,
        values={"content": "先建立十二个月应急储备", "status": MemoryStatus.DISABLED},
        fields_set={"content", "status"},
    )
    await service.delete_memory(created.id)

    assert fetched.user_id == user_id
    assert updated.embedding is None
    assert updated.content_hash == normalized_content_hash("先建立十二个月应急储备")
    assert created.id not in repository.memories
    assert all(requested == user_id for requested in repository.requested_user_ids)
    assert session.commits == 3
    assert [event["action"] for event in audit.events] == [
        "identity.user_memory_created",
        "identity.user_memory_updated",
        "identity.user_memory_deleted",
    ]
    assert all("应急储备" not in str(event) for event in audit.events)


@pytest.mark.asyncio
async def test_create_is_idempotent_and_rejects_key_reuse_for_other_payload() -> None:
    service, repository, audit, session = service_fixture(uuid4())
    first = await service.create_memory(
        category=MemoryCategory.PREFERENCE,
        title="偏好简洁",
        content="回答尽量简洁",
        idempotency_key="same-key",
    )
    replay = await service.create_memory(
        category=MemoryCategory.PREFERENCE,
        title="偏好简洁",
        content="回答尽量简洁",
        idempotency_key="same-key",
    )

    assert replay is first
    assert len(repository.memories) == 1
    assert len(audit.events) == 1
    assert session.commits == 1
    with pytest.raises(ConflictError, match="another memory"):
        await service.create_memory(
            category=MemoryCategory.GOAL,
            title="另一条",
            content="完全不同的内容",
            idempotency_key="same-key",
        )


@pytest.mark.asyncio
async def test_default_settings_are_created_and_patch_is_audited() -> None:
    service, repository, audit, session = service_fixture(uuid4())
    settings = await service.get_settings()
    assert settings.memory_enabled is None or settings.memory_enabled is True
    updated = await service.update_settings(
        values={"memory_enabled": False}, fields_set={"memory_enabled"}
    )

    assert updated.memory_enabled is False
    assert len(repository.settings) == 1
    assert session.commits == 2
    assert audit.events[0]["detail"] == {"changed_fields": ["memory_enabled"]}


@pytest.mark.asyncio
async def test_cross_user_memory_identifier_is_not_found() -> None:
    owner_id = uuid4()
    other_id = uuid4()
    service, repository, audit, session = service_fixture(other_id)
    foreign = UserMemory(
        id=uuid4(),
        user_id=owner_id,
        category=MemoryCategory.PERSONAL,
        title="私有背景",
        content="私有内容",
        status=MemoryStatus.ACTIVE,
        source_type=MemorySourceType.MANUAL_UI,
        content_hash=normalized_content_hash("私有内容"),
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    repository.memories[foreign.id] = foreign

    with pytest.raises(NotFoundError):
        await service.get_memory(foreign.id)
    with pytest.raises(NotFoundError):
        await service.update_memory(
            foreign.id, values={"title": "篡改"}, fields_set={"title"}
        )
    with pytest.raises(NotFoundError):
        await service.delete_memory(foreign.id)

    assert audit.events == []
    assert session.commits == 0
