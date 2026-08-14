"""真实 PostgreSQL 下的长期记忆 RLS 与外键归属测试。"""

from __future__ import annotations

import os
from uuid import uuid4

import pytest
from sqlalchemy import delete, select, text, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.models.identity import (
    MemoryCategory,
    MemorySourceType,
    MemoryStatus,
    User,
    UserMemory,
    UserMemorySettings,
    UserStatus,
)
from app.db.session import set_tenant_context
from app.services.memory import normalized_content_hash

INTEGRATION_DATABASE_URL = os.getenv("AURUM_RAG_INTEGRATION_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not INTEGRATION_DATABASE_URL,
    reason="AURUM_RAG_INTEGRATION_DATABASE_URL is not configured",
)


@pytest.mark.asyncio
async def test_memory_rows_cannot_be_read_updated_or_deleted_by_another_user() -> None:
    assert INTEGRATION_DATABASE_URL is not None
    engine = create_async_engine(INTEGRATION_DATABASE_URL)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    suffix = uuid4().hex

    async with factory() as session:
        owner = User(
            username=f"memory_owner_{suffix}",
            email=f"memory-owner-{suffix}@example.test",
            password_hash="integration-test-only",  # noqa: S106
            status=UserStatus.ACTIVE,
            token_version=0,
        )
        other = User(
            username=f"memory_other_{suffix}",
            email=f"memory-other-{suffix}@example.test",
            password_hash="integration-test-only",  # noqa: S106
            status=UserStatus.ACTIVE,
            token_version=0,
        )
        session.add_all([owner, other])
        await session.commit()
        owner_id, other_id = owner.id, other.id

    try:
        async with factory() as session:
            await set_tenant_context(session, owner_id)
            settings = UserMemorySettings(user_id=owner_id)
            memory = UserMemory(
                user_id=owner_id,
                category=MemoryCategory.GOAL,
                title="Owner only",
                content="Private memory",
                status=MemoryStatus.ACTIVE,
                source_type=MemorySourceType.MANUAL_UI,
                content_hash=normalized_content_hash("Private memory"),
            )
            session.add_all([settings, memory])
            await session.commit()
            memory_id = memory.id

        async with factory() as session:
            await set_tenant_context(session, other_id)
            visible_memory = await session.scalar(
                select(UserMemory).where(UserMemory.id == memory_id)
            )
            assert visible_memory is None
            updated = await session.execute(
                update(UserMemory).where(UserMemory.id == memory_id).values(title="stolen")
            )
            deleted = await session.execute(delete(UserMemory).where(UserMemory.id == memory_id))
            assert updated.rowcount == 0
            assert deleted.rowcount == 0
            await session.rollback()

        async with factory() as session:
            rows = (
                await session.execute(
                    text(
                        "SELECT relname, relrowsecurity, relforcerowsecurity FROM pg_class "
                        "JOIN pg_namespace ON pg_namespace.oid = pg_class.relnamespace "
                        "WHERE (nspname, relname) IN "
                        "(('identity', 'user_memory_settings'), "
                        "('identity', 'user_memories'), "
                        "('identity', 'user_memory_confirmations'), "
                        "('chat', 'agent_run_memories'))"
                    )
                )
            ).all()
            assert len(rows) == 4
            assert all(row.relrowsecurity and row.relforcerowsecurity for row in rows)
    finally:
        async with factory() as session:
            await set_tenant_context(session, owner_id)
            await session.execute(delete(UserMemory).where(UserMemory.user_id == owner_id))
            await session.execute(
                delete(UserMemorySettings).where(UserMemorySettings.user_id == owner_id)
            )
            await session.execute(delete(User).where(User.id.in_([owner_id, other_id])))
            await session.commit()
        await engine.dispose()
