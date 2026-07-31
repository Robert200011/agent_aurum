"""与 HTTP 连接解耦的进程内聊天运行协调器。"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from functools import partial
from uuid import UUID

from langgraph.checkpoint.base import BaseCheckpointSaver
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings
from app.errors import ApplicationError
from app.providers.model_provider import ChatModelProvider, RerankerProvider
from app.rag.embeddings.dashscope import DashScopeEmbeddingProvider
from app.services.answering import RagAnswerService
from app.services.chat import (
    ChatAnswerStreamEvent,
    ChatService,
    ChatStreamStarted,
    StreamingRun,
)
from app.services.retrieval import RagRetrievalService

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class BufferedChatEvent:
    sequence: int
    event: ChatAnswerStreamEvent


@dataclass(frozen=True, slots=True)
class ChatRunError:
    code: str
    message: str


type CoordinatedChatEvent = BufferedChatEvent | ChatRunError


@dataclass(slots=True)
class _RunFeed:
    conversation_id: UUID
    events: list[BufferedChatEvent] = field(default_factory=list)
    condition: asyncio.Condition = field(default_factory=asyncio.Condition)
    task: asyncio.Task[None] | None = None
    terminal: bool = False
    error: ChatRunError | None = None


class ChatRunCoordinator:
    """让模型生成继续运行，并允许后续请求重放同一次 SSE 事件。"""

    def __init__(
        self,
        *,
        settings: Settings,
        session_factory: async_sessionmaker[AsyncSession],
        chat_provider: ChatModelProvider,
        reranker_provider: RerankerProvider | None,
        checkpointer: BaseCheckpointSaver[str],
    ) -> None:
        self._settings = settings
        self._session_factory = session_factory
        self._chat_provider = chat_provider
        self._reranker_provider = reranker_provider
        self._checkpointer = checkpointer
        self._feeds: dict[UUID, _RunFeed] = {}

    def start(self, *, user_id: UUID, run: StreamingRun) -> None:
        """注册并启动唯一后台任务；调用前运行记录已经提交到数据库。"""

        if run.run_id in self._feeds:
            return
        feed = _RunFeed(
            conversation_id=run.conversation_id,
            events=[
                BufferedChatEvent(
                    sequence=1,
                    event=ChatStreamStarted(
                        message_id=run.message_id,
                        run_id=run.run_id,
                    ),
                )
            ]
        )
        self._feeds[run.run_id] = feed
        feed.task = asyncio.create_task(
            self._execute(user_id=user_id, run=run, feed=feed),
            name=f"chat-run-{run.run_id}",
        )

    def has_run(self, run_id: UUID) -> bool:
        return run_id in self._feeds

    async def subscribe(
        self,
        run_id: UUID,
        *,
        after_sequence: int = 0,
    ) -> AsyncIterator[CoordinatedChatEvent]:
        """重放游标后的事件，并等待后台运行进入终态。"""

        feed = self._feeds.get(run_id)
        if feed is None:
            return
        cursor = max(0, after_sequence)
        while True:
            async with feed.condition:
                await feed.condition.wait_for(partial(_feed_ready, feed, cursor))
                pending = [
                    event for event in feed.events if event.sequence > cursor
                ]
                terminal = feed.terminal
                error = feed.error
            for event in pending:
                cursor = event.sequence
                yield event
            if terminal:
                if error is not None:
                    yield error
                return

    async def cancel(self, run_id: UUID) -> bool:
        """只把显式用户操作转换为任务取消，普通 SSE 断开不会调用这里。"""

        feed = self._feeds.get(run_id)
        task = feed.task if feed is not None else None
        if task is None or task.done():
            return False
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        return True

    async def close(self) -> None:
        tasks = [
            feed.task
            for feed in self._feeds.values()
            if feed.task is not None and not feed.task.done()
        ]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def delete_thread(self, thread_id: UUID) -> None:
        """删除业务会话后同步清理其 LangGraph Checkpoint。"""

        await self._checkpointer.adelete_thread(str(thread_id))
        self._feeds = {
            run_id: feed
            for run_id, feed in self._feeds.items()
            if feed.conversation_id != thread_id
        }

    async def _execute(
        self,
        *,
        user_id: UUID,
        run: StreamingRun,
        feed: _RunFeed,
    ) -> None:
        try:
            async with self._session_factory() as session:
                retrieval = RagRetrievalService(
                    session=session,
                    actor_user_id=user_id,
                    embedding_provider=DashScopeEmbeddingProvider(self._settings),
                    reranker_provider=self._reranker_provider,
                    hybrid_candidate_multiplier=(
                        self._settings.rag_hybrid_candidate_multiplier
                    ),
                    rrf_k=self._settings.rag_rrf_k,
                )
                answering = RagAnswerService(
                    retrieval_service=retrieval,
                    chat_provider=self._chat_provider,
                    checkpointer=self._checkpointer,
                    retrieval_limit=self._settings.rag_retrieval_limit,
                    context_max_characters=self._settings.rag_context_max_characters,
                    context_source_max_characters=(
                        self._settings.rag_context_source_max_characters
                    ),
                )
                service = ChatService(
                    session=session,
                    user_id=user_id,
                    answer_service=answering,
                )
                async for event in service.execute_streaming_run(run):
                    await self._append(feed, event)
        except asyncio.CancelledError:
            raise
        except ApplicationError as exc:
            feed.error = ChatRunError(code=exc.code, message=exc.message)
        except Exception:
            logger.exception("unhandled detached chat run error", extra={"run_id": run.run_id})
            feed.error = ChatRunError(
                code="internal_error",
                message="an internal error occurred",
            )
        finally:
            async with feed.condition:
                feed.terminal = True
                feed.condition.notify_all()

    @staticmethod
    async def _append(feed: _RunFeed, event: ChatAnswerStreamEvent) -> None:
        async with feed.condition:
            feed.events.append(
                BufferedChatEvent(sequence=len(feed.events) + 1, event=event)
            )
            feed.condition.notify_all()


def _feed_ready(feed: _RunFeed, cursor: int) -> bool:
    return any(event.sequence > cursor for event in feed.events) or feed.terminal
