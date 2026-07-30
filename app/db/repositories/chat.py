"""会话、消息、引用和 Agent 运行记录的租户仓储。"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TypeVar, cast
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.chat import AgentRun, Conversation, Message, MessageCitation

ModelT = TypeVar("ModelT")


class ChatRepository:
    """所有读取同时包含显式 user_id 谓词和数据库 RLS。"""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, instance: ModelT) -> ModelT:
        self._session.add(instance)
        await self._session.flush()
        return instance

    async def add_all(self, instances: Sequence[object]) -> None:
        self._session.add_all(instances)
        await self._session.flush()

    async def get_conversation(
        self,
        *,
        user_id: UUID,
        conversation_id: UUID,
        for_update: bool = False,
    ) -> Conversation | None:
        statement = select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.user_id == user_id,
        )
        if for_update:
            statement = statement.with_for_update()
        return cast(Conversation | None, await self._session.scalar(statement))

    async def list_conversations(
        self,
        *,
        user_id: UUID,
        page: int,
        page_size: int,
    ) -> tuple[list[Conversation], int]:
        filters = (Conversation.user_id == user_id,)
        total = int(
            await self._session.scalar(
                select(func.count()).select_from(Conversation).where(*filters)
            )
            or 0
        )
        statement = (
            select(Conversation)
            .where(*filters)
            .order_by(Conversation.updated_at.desc(), Conversation.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list((await self._session.scalars(statement)).all()), total

    async def list_messages(
        self,
        *,
        user_id: UUID,
        conversation_id: UUID,
    ) -> list[Message]:
        statement = (
            select(Message)
            .where(
                Message.user_id == user_id,
                Message.conversation_id == conversation_id,
            )
            .order_by(Message.created_at, Message.id)
        )
        return list((await self._session.scalars(statement)).all())

    async def list_citations(
        self,
        *,
        user_id: UUID,
        message_ids: Sequence[UUID],
    ) -> list[MessageCitation]:
        if not message_ids:
            return []
        statement = (
            select(MessageCitation)
            .where(
                MessageCitation.user_id == user_id,
                MessageCitation.message_id.in_(message_ids),
            )
            .order_by(MessageCitation.message_id, MessageCitation.rank)
        )
        return list((await self._session.scalars(statement)).all())

    async def get_message(
        self,
        *,
        user_id: UUID,
        message_id: UUID,
        for_update: bool = False,
    ) -> Message | None:
        statement = select(Message).where(
            Message.id == message_id,
            Message.user_id == user_id,
        )
        if for_update:
            statement = statement.with_for_update()
        return cast(Message | None, await self._session.scalar(statement))

    async def get_agent_run(
        self,
        *,
        user_id: UUID,
        run_id: UUID,
        for_update: bool = False,
    ) -> AgentRun | None:
        statement = select(AgentRun).where(
            AgentRun.id == run_id,
            AgentRun.user_id == user_id,
        )
        if for_update:
            statement = statement.with_for_update()
        return cast(AgentRun | None, await self._session.scalar(statement))
