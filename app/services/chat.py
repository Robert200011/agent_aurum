"""普通用户会话管理与基础 RAG 问答持久化。"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.graph import RAG_GRAPH_VERSION
from app.agents.state import RagAnswerCompleted, RagAnswerDelta, RagAnswerResult
from app.chat.types import (
    AgentRunStatus,
    ConversationStatus,
    MessageRole,
    MessageStatus,
)
from app.db.models.chat import AgentRun, Conversation, Message, MessageCitation
from app.db.models.rag import AgentProject
from app.db.repositories.chat import ChatRepository
from app.db.repositories.rag import RagRepository
from app.db.session import set_tenant_context
from app.errors import ApplicationError, BusinessRuleError, NotFoundError
from app.services.answering import RagAnswerService

logger = logging.getLogger(__name__)

DEFAULT_CONVERSATION_TITLE = "新会话"
MAX_AUTOMATIC_TITLE_LENGTH = 60


@dataclass(frozen=True, slots=True)
class ConversationDetail:
    conversation: Conversation
    messages: list[Message]
    citations_by_message: dict[UUID, list[MessageCitation]]


@dataclass(frozen=True, slots=True)
class ConversationPage:
    items: list[Conversation]
    total: int
    page: int
    page_size: int


@dataclass(frozen=True, slots=True)
class PersistedAnswer:
    message: Message
    citations: list[MessageCitation]
    run: AgentRun


@dataclass(frozen=True, slots=True)
class ChatStreamStarted:
    """SSE 响应开始后可用于前端占位和诊断的持久化身份。"""

    message_id: UUID
    run_id: UUID


@dataclass(frozen=True, slots=True)
class ChatStreamDelta:
    """已从模型收到但尚未通过最终引用校验的文本增量。"""

    text: str


@dataclass(frozen=True, slots=True)
class ChatStreamCompleted:
    """最终回答和可信引用均已成功持久化。"""

    answer: PersistedAnswer


type ChatAnswerStreamEvent = ChatStreamStarted | ChatStreamDelta | ChatStreamCompleted


@dataclass(frozen=True, slots=True)
class _StreamingRun:
    project_id: UUID
    thread_id: UUID
    question: str
    message_id: UUID
    run_id: UUID
    started_at: datetime


class ChatService:
    """以短事务记录运行状态，并在模型调用后原子完成回答和引用。"""

    def __init__(
        self,
        *,
        session: AsyncSession,
        user_id: UUID,
        answer_service: RagAnswerService,
    ) -> None:
        self._session = session
        self._user_id = user_id
        self._answer_service = answer_service
        self._repository = ChatRepository(session)
        self._rag_repository = RagRepository(session)

    async def list_available_projects(self) -> list[AgentProject]:
        """List projects that can start a normal-user RAG conversation."""

        await self._prepare()
        return await self._rag_repository.list_available_chat_projects()

    async def create_conversation(
        self,
        *,
        project_id: UUID,
        title: str | None,
    ) -> Conversation:
        await self._prepare()
        project = await self._rag_repository.get_project(project_id)
        if project is None or project.deleted_at is not None:
            raise NotFoundError("agent project was not found")
        if project.status != "active":
            raise BusinessRuleError("conversation requires an active project")
        conversation = await self._repository.add(
            Conversation(
                user_id=self._user_id,
                project_id=project.id,
                title=title or DEFAULT_CONVERSATION_TITLE,
                status=ConversationStatus.ACTIVE.value,
            )
        )
        await self._session.commit()
        return conversation

    async def list_conversations(
        self,
        *,
        page: int,
        page_size: int,
    ) -> ConversationPage:
        await self._prepare()
        items, total = await self._repository.list_conversations(
            user_id=self._user_id,
            page=page,
            page_size=page_size,
        )
        return ConversationPage(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
        )

    async def get_conversation(self, conversation_id: UUID) -> ConversationDetail:
        await self._prepare()
        conversation = await self._owned_conversation(conversation_id)
        messages = await self._repository.list_messages(
            user_id=self._user_id,
            conversation_id=conversation.id,
        )
        citations = await self._repository.list_citations(
            user_id=self._user_id,
            message_ids=[message.id for message in messages],
        )
        citations_by_message: dict[UUID, list[MessageCitation]] = {}
        for citation in citations:
            citations_by_message.setdefault(citation.message_id, []).append(citation)
        return ConversationDetail(
            conversation=conversation,
            messages=messages,
            citations_by_message=citations_by_message,
        )

    async def update_conversation(
        self,
        conversation_id: UUID,
        *,
        title: str | None,
        status: ConversationStatus | None,
        fields_set: set[str],
    ) -> Conversation:
        await self._prepare()
        conversation = await self._owned_conversation(conversation_id, for_update=True)
        if "title" in fields_set:
            conversation.title = title or conversation.title
        if "status" in fields_set:
            conversation.status = (status or ConversationStatus.ACTIVE).value
        conversation.updated_at = datetime.now(UTC)
        await self._session.commit()
        return conversation

    async def answer(
        self,
        *,
        conversation_id: UUID,
        question: str,
        trace_id: str | None,
    ) -> PersistedAnswer:
        """记录运行起点，调用 RAG 图，并完成或失败该运行。"""

        await self._prepare()
        conversation = await self._owned_conversation(conversation_id, for_update=True)
        if conversation.status != ConversationStatus.ACTIVE.value:
            raise BusinessRuleError("only active conversations can receive messages")
        if conversation.project_id is None:
            raise BusinessRuleError("conversation project is no longer available")

        normalized_question = question.strip()
        if not normalized_question or len(normalized_question) > 2_000:
            raise BusinessRuleError("question is not valid")
        started_at = datetime.now(UTC)
        user_message = Message(
            conversation_id=conversation.id,
            user_id=self._user_id,
            role=MessageRole.USER.value,
            content=normalized_question,
            status=MessageStatus.COMPLETED.value,
            created_at=started_at,
        )
        assistant_message = Message(
            conversation_id=conversation.id,
            user_id=self._user_id,
            role=MessageRole.ASSISTANT.value,
            content="",
            status=MessageStatus.PENDING.value,
            created_at=started_at + timedelta(microseconds=1),
        )
        await self._repository.add_all([user_message, assistant_message])
        run = await self._repository.add(
            AgentRun(
                user_id=self._user_id,
                conversation_id=conversation.id,
                message_id=assistant_message.id,
                thread_id=conversation.id,
                trace_id=trace_id[:64] if trace_id else None,
                status=AgentRunStatus.RUNNING.value,
                graph_version=RAG_GRAPH_VERSION,
                detail={},
                started_at=started_at,
            )
        )
        if conversation.title == DEFAULT_CONVERSATION_TITLE:
            conversation.title = _automatic_title(normalized_question)
        conversation.updated_at = started_at
        await self._session.commit()

        try:
            result = await self._answer_service.answer(
                project_id=conversation.project_id,
                question=normalized_question,
                thread_id=conversation.id,
            )
            await self._prepare()
            assistant = await self._required_message(assistant_message.id, for_update=True)
            persisted_run = await self._required_run(run.id, for_update=True)
            completed_at = datetime.now(UTC)
            assistant.content = result.answer
            assistant.status = MessageStatus.COMPLETED.value
            assistant.latency_ms = result.latency_ms
            if result.completion is not None:
                assistant.model = result.completion.model
                if result.completion.usage is not None:
                    assistant.prompt_tokens = result.completion.usage.prompt_tokens
                    assistant.completion_tokens = result.completion.usage.completion_tokens
            citations = [
                MessageCitation(
                    user_id=self._user_id,
                    message_id=assistant.id,
                    chunk_id=citation.chunk_id,
                    rank=citation.citation_id,
                    score=citation.score,
                    quote_snapshot=citation.quote,
                    source_snapshot=citation.source_snapshot(),
                )
                for citation in result.citations
            ]
            await self._repository.add_all(citations)
            persisted_run.status = AgentRunStatus.COMPLETED.value
            persisted_run.latency_ms = result.latency_ms
            persisted_run.completed_at = completed_at
            persisted_run.detail = {
                "retrieval_source": "hybrid",
                "retrieval_result_count": len(result.retrieval.items),
                "citation_count": len(citations),
                "embedding_model": result.retrieval.embedding_model,
                "chat_model": result.completion.model if result.completion else None,
                "chat_request_id": (
                    result.completion.request_id if result.completion else None
                ),
                "finish_reason": (
                    result.completion.finish_reason if result.completion else "no_context"
                ),
                "checkpoint_id": result.checkpoint_id,
                "checkpoint_namespace": "",
            }
            await self._session.commit()
            return PersistedAnswer(
                message=assistant,
                citations=citations,
                run=persisted_run,
            )
        except ApplicationError as exc:
            await self._mark_failed(
                message_id=assistant_message.id,
                run_id=run.id,
                error_code=exc.code,
                started_at=started_at,
            )
            raise
        except Exception:
            await self._mark_failed(
                message_id=assistant_message.id,
                run_id=run.id,
                error_code="internal_error",
                started_at=started_at,
            )
            raise

    async def stream_answer(
        self,
        *,
        conversation_id: UUID,
        question: str,
        trace_id: str | None,
    ) -> AsyncIterator[ChatAnswerStreamEvent]:
        """持久化流式运行，并仅在可信引用校验成功后提交最终回答。"""

        streaming_run = await self._start_streaming_run(
            conversation_id=conversation_id,
            question=question,
            trace_id=trace_id,
        )
        yield ChatStreamStarted(
            message_id=streaming_run.message_id,
            run_id=streaming_run.run_id,
        )
        completed = False
        try:
            async for event in self._answer_service.stream(
                project_id=streaming_run.project_id,
                question=streaming_run.question,
                thread_id=streaming_run.thread_id,
            ):
                if isinstance(event, RagAnswerDelta):
                    yield ChatStreamDelta(event.text)
                    continue
                if not isinstance(event, RagAnswerCompleted):
                    raise RuntimeError("unsupported RAG stream event")
                persisted = await self._persist_streamed_answer(
                    streaming_run=streaming_run,
                    result=event.result,
                )
                completed = True
                yield ChatStreamCompleted(persisted)
            if not completed:
                raise RuntimeError("RAG stream ended without a completion event")
        except asyncio.CancelledError:
            if not completed:
                await self._mark_stream_terminal(
                    streaming_run=streaming_run,
                    message_status=MessageStatus.CANCELLED,
                    run_status=AgentRunStatus.CANCELLED,
                    error_code="client_disconnected",
                )
            raise
        except ApplicationError as exc:
            if not completed:
                await self._mark_stream_terminal(
                    streaming_run=streaming_run,
                    message_status=MessageStatus.FAILED,
                    run_status=AgentRunStatus.FAILED,
                    error_code=exc.code,
                )
            raise
        except Exception:
            if not completed:
                await self._mark_stream_terminal(
                    streaming_run=streaming_run,
                    message_status=MessageStatus.FAILED,
                    run_status=AgentRunStatus.FAILED,
                    error_code="internal_error",
                )
            raise

    async def _start_streaming_run(
        self,
        *,
        conversation_id: UUID,
        question: str,
        trace_id: str | None,
    ) -> _StreamingRun:
        await self._prepare()
        conversation = await self._owned_conversation(conversation_id, for_update=True)
        if conversation.status != ConversationStatus.ACTIVE.value:
            raise BusinessRuleError("only active conversations can receive messages")
        if conversation.project_id is None:
            raise BusinessRuleError("conversation project is no longer available")

        normalized_question = question.strip()
        if not normalized_question or len(normalized_question) > 2_000:
            raise BusinessRuleError("question is not valid")
        started_at = datetime.now(UTC)
        user_message = Message(
            conversation_id=conversation.id,
            user_id=self._user_id,
            role=MessageRole.USER.value,
            content=normalized_question,
            status=MessageStatus.COMPLETED.value,
            created_at=started_at,
        )
        assistant_message = Message(
            conversation_id=conversation.id,
            user_id=self._user_id,
            role=MessageRole.ASSISTANT.value,
            content="",
            status=MessageStatus.STREAMING.value,
            created_at=started_at + timedelta(microseconds=1),
        )
        await self._repository.add_all([user_message, assistant_message])
        run = await self._repository.add(
            AgentRun(
                user_id=self._user_id,
                conversation_id=conversation.id,
                message_id=assistant_message.id,
                thread_id=conversation.id,
                trace_id=trace_id[:64] if trace_id else None,
                status=AgentRunStatus.RUNNING.value,
                graph_version=RAG_GRAPH_VERSION,
                detail={"response_mode": "sse"},
                started_at=started_at,
            )
        )
        if conversation.title == DEFAULT_CONVERSATION_TITLE:
            conversation.title = _automatic_title(normalized_question)
        conversation.updated_at = started_at
        await self._session.commit()
        return _StreamingRun(
            project_id=conversation.project_id,
            thread_id=conversation.id,
            question=normalized_question,
            message_id=assistant_message.id,
            run_id=run.id,
            started_at=started_at,
        )

    async def _persist_streamed_answer(
        self,
        *,
        streaming_run: _StreamingRun,
        result: RagAnswerResult,
    ) -> PersistedAnswer:
        await self._prepare()
        assistant = await self._required_message(
            streaming_run.message_id,
            for_update=True,
        )
        run = await self._required_run(streaming_run.run_id, for_update=True)
        completed_at = datetime.now(UTC)
        assistant.content = result.answer
        assistant.status = MessageStatus.COMPLETED.value
        assistant.latency_ms = result.latency_ms
        if result.completion is not None:
            assistant.model = result.completion.model
            if result.completion.usage is not None:
                assistant.prompt_tokens = result.completion.usage.prompt_tokens
                assistant.completion_tokens = result.completion.usage.completion_tokens
        citations = [
            MessageCitation(
                user_id=self._user_id,
                message_id=assistant.id,
                chunk_id=citation.chunk_id,
                rank=citation.citation_id,
                score=citation.score,
                quote_snapshot=citation.quote,
                source_snapshot=citation.source_snapshot(),
            )
            for citation in result.citations
        ]
        await self._repository.add_all(citations)
        run.status = AgentRunStatus.COMPLETED.value
        run.latency_ms = result.latency_ms
        run.completed_at = completed_at
        run.detail = {
            "response_mode": "sse",
            "retrieval_source": "hybrid",
            "retrieval_result_count": len(result.retrieval.items),
            "citation_count": len(citations),
            "embedding_model": result.retrieval.embedding_model,
            "chat_model": result.completion.model if result.completion else None,
            "chat_request_id": (
                result.completion.request_id if result.completion else None
            ),
            "finish_reason": (
                result.completion.finish_reason if result.completion else "no_context"
            ),
            "checkpoint_id": result.checkpoint_id,
            "checkpoint_namespace": "",
        }
        await self._session.commit()
        return PersistedAnswer(message=assistant, citations=citations, run=run)

    async def _mark_stream_terminal(
        self,
        *,
        streaming_run: _StreamingRun,
        message_status: MessageStatus,
        run_status: AgentRunStatus,
        error_code: str,
    ) -> None:
        await self._session.rollback()
        try:
            await self._prepare()
            message = await self._required_message(
                streaming_run.message_id,
                for_update=True,
            )
            run = await self._required_run(streaming_run.run_id, for_update=True)
            completed_at = datetime.now(UTC)
            message.content = ""
            message.status = message_status.value
            message.latency_ms = max(
                0,
                round((completed_at - streaming_run.started_at).total_seconds() * 1000),
            )
            run.status = run_status.value
            run.error_code = error_code[:64]
            run.latency_ms = message.latency_ms
            run.completed_at = completed_at
            run.detail = {"response_mode": "sse"}
            await self._session.commit()
        except Exception:
            await self._session.rollback()
            logger.exception("unable to persist terminal streaming RAG state")

    async def _mark_failed(
        self,
        *,
        message_id: UUID,
        run_id: UUID,
        error_code: str,
        started_at: datetime,
    ) -> None:
        await self._session.rollback()
        try:
            await self._prepare()
            message = await self._required_message(message_id, for_update=True)
            run = await self._required_run(run_id, for_update=True)
            completed_at = datetime.now(UTC)
            message.status = MessageStatus.FAILED.value
            message.latency_ms = max(
                0,
                round((completed_at - started_at).total_seconds() * 1000),
            )
            run.status = AgentRunStatus.FAILED.value
            run.error_code = error_code[:64]
            run.latency_ms = message.latency_ms
            run.completed_at = completed_at
            await self._session.commit()
        except Exception:
            await self._session.rollback()
            logger.exception("unable to persist failed RAG run state")

    async def _prepare(self) -> None:
        await set_tenant_context(self._session, self._user_id)

    async def _owned_conversation(
        self,
        conversation_id: UUID,
        *,
        for_update: bool = False,
    ) -> Conversation:
        conversation = await self._repository.get_conversation(
            user_id=self._user_id,
            conversation_id=conversation_id,
            for_update=for_update,
        )
        if conversation is None:
            raise NotFoundError("conversation was not found")
        return conversation

    async def _required_message(
        self,
        message_id: UUID,
        *,
        for_update: bool,
    ) -> Message:
        message = await self._repository.get_message(
            user_id=self._user_id,
            message_id=message_id,
            for_update=for_update,
        )
        if message is None:
            raise RuntimeError("persisted assistant message is unavailable")
        return message

    async def _required_run(self, run_id: UUID, *, for_update: bool) -> AgentRun:
        run = await self._repository.get_agent_run(
            user_id=self._user_id,
            run_id=run_id,
            for_update=for_update,
        )
        if run is None:
            raise RuntimeError("persisted agent run is unavailable")
        return run


def _automatic_title(question: str) -> str:
    compact = " ".join(question.split())
    return compact[:MAX_AUTOMATIC_TITLE_LENGTH] or DEFAULT_CONVERSATION_TITLE
