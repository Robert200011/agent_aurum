"""真实 PostgreSQL 下的用户设置 RLS 隔离测试。"""

from __future__ import annotations

import os
from uuid import uuid4

import pytest
from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.models.identity import User, UserPreference, UserProfile, UserStatus
from app.db.session import set_tenant_context

INTEGRATION_DATABASE_URL = os.getenv("AURUM_RAG_INTEGRATION_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not INTEGRATION_DATABASE_URL,
    reason="AURUM_RAG_INTEGRATION_DATABASE_URL is not configured",
)


@pytest.mark.asyncio
async def test_user_profile_and_preferences_are_hidden_from_other_users() -> None:
    assert INTEGRATION_DATABASE_URL is not None
    engine = create_async_engine(INTEGRATION_DATABASE_URL)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    suffix = uuid4().hex

    async with factory() as session:
        owner = User(
            username=f"settings_owner_{suffix}",
            email=f"settings-owner-{suffix}@example.test",
            password_hash="integration-test-only",  # noqa: S106
            status=UserStatus.ACTIVE,
            token_version=0,
        )
        other = User(
            username=f"settings_other_{suffix}",
            email=f"settings-other-{suffix}@example.test",
            password_hash="integration-test-only",  # noqa: S106
            status=UserStatus.ACTIVE,
            token_version=0,
        )
        session.add_all([owner, other])
        await session.commit()
        owner_id = owner.id
        other_id = other.id

    try:
        async with factory() as session:
            await set_tenant_context(session, owner_id)
            profile = UserProfile(user_id=owner_id, display_name="Private name")
            preferences = UserPreference(user_id=owner_id, base_currency="USD")
            session.add_all([profile, preferences])
            await session.commit()
            profile_id = profile.id
            preferences_id = preferences.id

        async with factory() as session:
            await set_tenant_context(session, other_id)
            assert (
                await session.scalar(select(UserProfile).where(UserProfile.id == profile_id))
                is None
            )
            assert (
                await session.scalar(
                    select(UserPreference).where(UserPreference.id == preferences_id)
                )
                is None
            )

        async with factory() as session:
            rows = (
                await session.execute(
                    text(
                        "SELECT relname, relrowsecurity, relforcerowsecurity FROM pg_class "
                        "JOIN pg_namespace ON pg_namespace.oid = pg_class.relnamespace "
                        "WHERE nspname = 'identity' AND relname IN "
                        "('user_profiles', 'user_preferences')"
                    )
                )
            ).all()
            assert len(rows) == 2
            assert all(row.relrowsecurity and row.relforcerowsecurity for row in rows)
    finally:
        async with factory() as session:
            await set_tenant_context(session, owner_id)
            await session.execute(delete(UserPreference).where(UserPreference.user_id == owner_id))
            await session.execute(delete(UserProfile).where(UserProfile.user_id == owner_id))
            await session.execute(delete(User).where(User.id.in_([owner_id, other_id])))
            await session.commit()
        await engine.dispose()
