"""会话、消息、引用和 Agent 运行记录的租户仓储。"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import TypeVar, cast
from uuid import UUID

from sqlalchemy import delete, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.db.models.chat import (
    AgentRun,
    AgentToolCall,
    Conversation,
    Message,
    MessageCitation,
    MessageEvidence,
)

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
        search: str | None = None,
    ) -> tuple[list[Conversation], int]:
        filters: list[ColumnElement[bool]] = [Conversation.user_id == user_id]
        if search:
            pattern = f"%{search.strip()}%"
            matching_message = exists(
                select(Message.id).where(
                    Message.conversation_id == Conversation.id,
                    Message.user_id == user_id,
                    Message.content.ilike(pattern),
                )
            )
            filters.append(
                or_(
                    Conversation.title.ilike(pattern),
                    matching_message,
                )
            )
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

    async def list_message_evidence(
        self,
        *,
        user_id: UUID,
        message_ids: Sequence[UUID],
    ) -> list[MessageEvidence]:
        """按消息和展示顺序加载当前租户的财务证据。"""

        if not message_ids:
            return []
        statement = (
            select(MessageEvidence)
            .where(
                MessageEvidence.user_id == user_id,
                MessageEvidence.message_id.in_(message_ids),
            )
            .order_by(MessageEvidence.message_id, MessageEvidence.rank)
        )
        return list((await self._session.scalars(statement)).all())

    async def list_agent_runs_for_messages(
        self,
        *,
        user_id: UUID,
        message_ids: Sequence[UUID],
    ) -> list[AgentRun]:
        """按新到旧加载消息运行，供历史回答恢复最新元数据。"""

        if not message_ids:
            return []
        statement = (
            select(AgentRun)
            .where(
                AgentRun.user_id == user_id,
                AgentRun.message_id.in_(message_ids),
            )
            .order_by(AgentRun.message_id, AgentRun.created_at.desc(), AgentRun.id.desc())
        )
        return list((await self._session.scalars(statement)).all())

    async def list_agent_tool_calls(
        self,
        *,
        user_id: UUID,
        run_id: UUID,
    ) -> list[AgentToolCall]:
        statement = (
            select(AgentToolCall)
            .where(
                AgentToolCall.user_id == user_id,
                AgentToolCall.run_id == run_id,
            )
            .order_by(AgentToolCall.created_at, AgentToolCall.id)
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

    async def get_latest_agent_run(
        self,
        *,
        user_id: UUID,
        conversation_id: UUID,
    ) -> AgentRun | None:
        statement = (
            select(AgentRun)
            .where(
                AgentRun.user_id == user_id,
                AgentRun.conversation_id == conversation_id,
            )
            .order_by(AgentRun.created_at.desc(), AgentRun.id.desc())
            .limit(1)
        )
        return cast(AgentRun | None, await self._session.scalar(statement))

    async def get_running_agent_run(
        self,
        *,
        user_id: UUID,
        conversation_id: UUID,
    ) -> AgentRun | None:
        statement = (
            select(AgentRun)
            .where(
                AgentRun.user_id == user_id,
                AgentRun.conversation_id == conversation_id,
                AgentRun.status.in_(("queued", "running")),
            )
            .order_by(AgentRun.created_at.desc(), AgentRun.id.desc())
            .limit(1)
        )
        return cast(AgentRun | None, await self._session.scalar(statement))

    async def get_previous_user_message(
        self,
        *,
        user_id: UUID,
        conversation_id: UUID,
        before: datetime,
    ) -> Message | None:
        statement = (
            select(Message)
            .where(
                Message.user_id == user_id,
                Message.conversation_id == conversation_id,
                Message.role == "user",
                Message.created_at < before,
            )
            .order_by(Message.created_at.desc(), Message.id.desc())
            .limit(1)
        )
        return cast(Message | None, await self._session.scalar(statement))

    async def delete_message_citations(
        self,
        *,
        user_id: UUID,
        message_id: UUID,
    ) -> None:
        await self._session.execute(
            delete(MessageCitation).where(
                MessageCitation.user_id == user_id,
                MessageCitation.message_id == message_id,
            )
        )

    async def delete_message_evidence(
        self,
        *,
        user_id: UUID,
        message_id: UUID,
    ) -> None:
        await self._session.execute(
            delete(MessageEvidence).where(
                MessageEvidence.user_id == user_id,
                MessageEvidence.message_id == message_id,
            )
        )

    async def delete_conversation(self, conversation: Conversation) -> None:
        await self._session.delete(conversation)
