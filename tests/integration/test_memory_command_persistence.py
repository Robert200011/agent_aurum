"""真实 PostgreSQL 下聊天记忆保存的消息幂等和确认隔离测试。"""

from __future__ import annotations

import os
from uuid import uuid4

import pytest
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.models.chat import Conversation, Message
from app.db.models.identity import User, UserMemory, UserMemoryConfirmation, UserStatus
from app.db.session import set_tenant_context
from app.memory.contracts import MemoryDecision
from app.services.memory_commands import MemoryCommandService, MemorySaveResultKind

INTEGRATION_DATABASE_URL = os.getenv("AURUM_RAG_INTEGRATION_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not INTEGRATION_DATABASE_URL,
    reason="AURUM_RAG_INTEGRATION_DATABASE_URL is not configured",
)


class FixedProvider:
    def __init__(self, decision: MemoryDecision) -> None:
        self.decision = decision
        self.calls = 0

    async def decide(self, _: str) -> MemoryDecision:
        self.calls += 1
        return self.decision


@pytest.mark.asyncio
async def test_chat_memory_save_replays_by_source_message() -> None:
    assert INTEGRATION_DATABASE_URL is not None
    engine = create_async_engine(INTEGRATION_DATABASE_URL)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    suffix = uuid4().hex
    async with factory() as session:
        user = User(
            username=f"memory_command_{suffix}",
            email=f"memory-command-{suffix}@example.test",
            password_hash="integration-test-only",  # noqa: S106
            status=UserStatus.ACTIVE,
            token_version=0,
        )
        session.add(user)
        await session.commit()
        user_id = user.id
    try:
        async with factory() as session:
            await set_tenant_context(session, user_id)
            conversation = Conversation(user_id=user_id, title="Memory", status="active")
            session.add(conversation)
            await session.flush()
            message = Message(
                conversation_id=conversation.id,
                user_id=user_id,
                role="user",
                content="请记住：我偏好低波动方案",
                status="completed",
            )
            session.add(message)
            await session.commit()
            message_id = message.id
            provider = FixedProvider(
                MemoryDecision(
                    decision="save",
                    reason_code="explicit_save_request",
                    items=[
                        {
                            "category": "preference",
                            "title": "偏好低波动",
                            "content": "投资分析优先考虑低波动方案。",
                            "evidence": "我偏好低波动方案",
                        }
                    ],
                )
            )
            service = MemoryCommandService(
                session=session,
                user_id=user_id,
                decision_provider=provider,  # type: ignore[arg-type]
                max_items=200,
                confirmation_ttl_seconds=600,
            )
            first = await service.process_message(
                source_message_id=message_id,
                current_user_message=message.content,
            )
            replay = await service.process_message(
                source_message_id=message_id,
                current_user_message=message.content,
            )
            assert first.save_results[0].result == MemorySaveResultKind.SAVED
            assert replay.save_results[0].memory_id == first.save_results[0].memory_id
            assert provider.calls == 1
    finally:
        async with factory() as session:
            await set_tenant_context(session, user_id)
            await session.execute(delete(UserMemory).where(UserMemory.user_id == user_id))
            await session.execute(
                delete(UserMemoryConfirmation).where(
                    UserMemoryConfirmation.user_id == user_id
                )
            )
            await session.execute(delete(Conversation).where(Conversation.user_id == user_id))
            await session.execute(delete(User).where(User.id == user_id))
            await session.commit()
        await engine.dispose()
