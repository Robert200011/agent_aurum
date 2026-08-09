"""普通用户会话管理与基础 RAG 问答持久化。"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.graph import RAG_GRAPH_VERSION
from app.agents.policies.rag_prompt import HIGH_RISK_INVESTMENT_DISCLAIMER
from app.agents.state import (
    RagAnswerCompleted,
    RagAnswerDelta,
    RagAnswerResult,
    RagAnswerStage,
)
from app.chat.finance_evidence import build_finance_persistence_record
from app.chat.types import (
    AgentRunStatus,
    ConversationStatus,
    MessageRole,
    MessageStatus,
)
from app.db.models.chat import (
    AgentRun,
    AgentToolCall,
    Conversation,
    Message,
    MessageCitation,
    MessageEvidence,
)
from app.db.repositories.chat import ChatRepository
from app.db.session import set_tenant_context
from app.errors import (
    ApplicationError,
    BusinessRuleError,
    ConflictError,
    NotFoundError,
)
from app.services.answering import RagAnswerService

logger = logging.getLogger(__name__)

DEFAULT_CONVERSATION_TITLE = "新会话"
MAX_AUTOMATIC_TITLE_LENGTH = 60


@dataclass(frozen=True, slots=True)
class ConversationDetail:
    conversation: Conversation
    messages: list[Message]
    citations_by_message: dict[UUID, list[MessageCitation]]
    evidence_by_message: dict[UUID, list[MessageEvidence]]
    runs_by_message: dict[UUID, AgentRun]


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
    evidence: list[MessageEvidence]
    data_as_of: datetime | None = None
    risk_notice: str | None = None


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
class ChatStreamStatus:
    """可直接展示给用户的有限生成阶段，不暴露内部图节点。"""

    stage: Literal[
        "understanding",
        "retrieving",
        "querying_finance",
        "analyzing",
        "generating",
        "finalizing",
    ]


@dataclass(frozen=True, slots=True)
class ChatStreamCompleted:
    """最终回答和可信引用均已成功持久化。"""

    answer: PersistedAnswer


type ChatAnswerStreamEvent = (
    ChatStreamStarted | ChatStreamStatus | ChatStreamDelta | ChatStreamCompleted
)


@dataclass(frozen=True, slots=True)
class StreamingRun:
    conversation_id: UUID
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

    @property
    def user_id(self) -> UUID:
        return self._user_id

    async def create_conversation(
        self,
        *,
        title: str | None,
    ) -> Conversation:
        await self._prepare()
        conversation = await self._repository.add(
            Conversation(
                user_id=self._user_id,
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
        search: str | None = None,
    ) -> ConversationPage:
        await self._prepare()
        normalized_search = search.strip() if search else None
        items, total = await self._repository.list_conversations(
            user_id=self._user_id,
            page=page,
            page_size=page_size,
            search=normalized_search or None,
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
        evidence = await self._repository.list_message_evidence(
            user_id=self._user_id,
            message_ids=[message.id for message in messages],
        )
        evidence_by_message: dict[UUID, list[MessageEvidence]] = {}
        for item in evidence:
            evidence_by_message.setdefault(item.message_id, []).append(item)
        runs = await self._repository.list_agent_runs_for_messages(
            user_id=self._user_id,
            message_ids=[message.id for message in messages],
        )
        runs_by_message: dict[UUID, AgentRun] = {}
        for run in runs:
            if run.message_id is not None:
                runs_by_message.setdefault(run.message_id, run)
        return ConversationDetail(
            conversation=conversation,
            messages=messages,
            citations_by_message=citations_by_message,
            evidence_by_message=evidence_by_message,
            runs_by_message=runs_by_message,
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

    async def delete_conversation(self, conversation_id: UUID) -> None:
        """永久删除当前用户会话；运行中的问答必须先显式停止。"""

        await self._prepare()
        conversation = await self._owned_conversation(conversation_id, for_update=True)
        running = await self._repository.get_running_agent_run(
            user_id=self._user_id,
            conversation_id=conversation.id,
        )
        if running is not None:
            raise ConflictError("stop the running answer before deleting the conversation")
        await self._repository.delete_conversation(conversation)
        await self._session.commit()

    async def get_latest_run(self, conversation_id: UUID) -> AgentRun | None:
        await self._prepare()
        conversation = await self._owned_conversation(conversation_id)
        return await self._repository.get_latest_agent_run(
            user_id=self._user_id,
            conversation_id=conversation.id,
        )

    async def get_run(self, conversation_id: UUID, run_id: UUID) -> AgentRun:
        await self._prepare()
        await self._owned_conversation(conversation_id)
        run = await self._repository.get_agent_run(
            user_id=self._user_id,
            run_id=run_id,
            for_update=False,
        )
        if run is None:
            raise NotFoundError("agent run was not found")
        if run.conversation_id != conversation_id:
            raise NotFoundError("agent run was not found")
        return run

    async def persisted_answer_for_run(
        self,
        conversation_id: UUID,
        run_id: UUID,
    ) -> PersistedAnswer | None:
        run = await self.get_run(conversation_id, run_id)
        if run.status != AgentRunStatus.COMPLETED.value or run.message_id is None:
            return None
        message = await self._required_message(run.message_id, for_update=False)
        citations = await self._repository.list_citations(
            user_id=self._user_id,
            message_ids=[message.id],
        )
        evidence = await self._repository.list_message_evidence(
            user_id=self._user_id,
            message_ids=[message.id],
        )
        return PersistedAnswer(
            message=message,
            citations=citations,
            run=run,
            evidence=evidence,
            data_as_of=_detail_datetime(run.detail.get("data_as_of")),
            risk_notice=_detail_text(run.detail.get("risk_notice")),
        )

    async def cancel_run(self, conversation_id: UUID, run_id: UUID) -> AgentRun:
        """把无法在当前进程定位任务的运行安全收敛为取消终态。"""

        await self._prepare()
        await self._owned_conversation(conversation_id)
        run = await self._repository.get_agent_run(
            user_id=self._user_id,
            run_id=run_id,
            for_update=True,
        )
        if run is None:
            raise NotFoundError("agent run was not found")
        if run.conversation_id != conversation_id:
            raise NotFoundError("agent run was not found")
        if run.status not in {
            AgentRunStatus.QUEUED.value,
            AgentRunStatus.RUNNING.value,
        }:
            raise ConflictError("agent run is already in a terminal state")
        completed_at = datetime.now(UTC)
        run.status = AgentRunStatus.CANCELLED.value
        run.error_code = "user_cancelled"
        run.completed_at = completed_at
        if run.started_at is not None:
            run.latency_ms = max(
                0,
                round((completed_at - run.started_at).total_seconds() * 1000),
            )
        if run.message_id is not None:
            message = await self._required_message(run.message_id, for_update=True)
            message.status = MessageStatus.CANCELLED.value
            message.content = ""
            message.latency_ms = run.latency_ms
        await self._session.commit()
        return run

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
            evidence = await self._persist_finance_evidence(
                run_id=persisted_run.id,
                message_id=assistant.id,
                results=result.finance_results,
            )
            persisted_run.status = AgentRunStatus.COMPLETED.value
            persisted_run.latency_ms = result.latency_ms
            persisted_run.completed_at = completed_at
            persisted_run.detail = {
                "intent": result.plan.intent if result.plan is not None else "knowledge",
                "planner_mode": _planner_mode(result),
                "route_reason": result.plan.route_reason if result.plan is not None else None,
                "planner_confidence": (result.plan.confidence if result.plan is not None else None),
                "retrieval_source": (
                    "hybrid" if result.retrieval.knowledge_base_ids else "not_requested"
                ),
                "retrieval_result_count": len(result.retrieval.items),
                "citation_count": len(citations),
                "embedding_model": result.retrieval.embedding_model,
                "chat_model": result.completion.model if result.completion else None,
                "chat_request_id": (result.completion.request_id if result.completion else None),
                "finish_reason": (
                    result.completion.finish_reason if result.completion else "no_context"
                ),
                "checkpoint_id": result.checkpoint_id,
                "checkpoint_namespace": "",
                "data_as_of": (
                    result.data_as_of.isoformat() if result.data_as_of is not None else None
                ),
                "finance_tool_count": len(result.finance_results),
                "finance_tool_statuses": [
                    tool_result.status.value for tool_result in result.finance_results
                ],
                "risk_policy": (result.plan.risk_policy if result.plan is not None else "standard"),
                "risk_notice": _risk_notice(result),
            }
            await self._session.commit()
            return PersistedAnswer(
                message=assistant,
                citations=citations,
                run=persisted_run,
                evidence=evidence,
                data_as_of=result.data_as_of,
                risk_notice=_risk_notice(result),
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

        streaming_run = await self.start_streaming_run(
            conversation_id=conversation_id,
            question=question,
            trace_id=trace_id,
        )
        yield ChatStreamStarted(
            message_id=streaming_run.message_id,
            run_id=streaming_run.run_id,
        )
        async for event in self.execute_streaming_run(streaming_run):
            yield event

    async def start_streaming_run(
        self,
        *,
        conversation_id: UUID,
        question: str,
        trace_id: str | None,
    ) -> StreamingRun:
        """创建可由独立后台任务继续执行的持久化运行。"""

        return await self._start_streaming_run(
            conversation_id=conversation_id,
            question=question,
            trace_id=trace_id,
        )

    async def regenerate_streaming_run(
        self,
        *,
        conversation_id: UUID,
        message_id: UUID,
        trace_id: str | None,
    ) -> StreamingRun:
        """复用原助手消息重新生成，保留旧 AgentRun 作为审计记录。"""

        await self._prepare()
        conversation = await self._owned_conversation(conversation_id, for_update=True)
        if conversation.status != ConversationStatus.ACTIVE.value:
            raise BusinessRuleError("only active conversations can regenerate answers")
        await self._ensure_no_running_run(conversation.id)
        assistant = await self._repository.get_message(
            user_id=self._user_id,
            message_id=message_id,
            for_update=True,
        )
        if assistant is None:
            raise NotFoundError("assistant message was not found")
        if (
            assistant.conversation_id != conversation.id
            or assistant.role != MessageRole.ASSISTANT.value
            or assistant.status
            not in {
                MessageStatus.COMPLETED.value,
                MessageStatus.FAILED.value,
                MessageStatus.CANCELLED.value,
            }
        ):
            raise BusinessRuleError("only a terminal assistant answer can be regenerated")
        user_message = await self._repository.get_previous_user_message(
            user_id=self._user_id,
            conversation_id=conversation.id,
            before=assistant.created_at,
        )
        if user_message is None:
            raise BusinessRuleError("the source question for this answer is unavailable")

        started_at = datetime.now(UTC)
        await self._repository.delete_message_citations(
            user_id=self._user_id,
            message_id=assistant.id,
        )
        await self._repository.delete_message_evidence(
            user_id=self._user_id,
            message_id=assistant.id,
        )
        assistant.content = ""
        assistant.status = MessageStatus.STREAMING.value
        assistant.model = None
        assistant.prompt_tokens = None
        assistant.completion_tokens = None
        assistant.latency_ms = None
        run = await self._repository.add(
            AgentRun(
                user_id=self._user_id,
                conversation_id=conversation.id,
                message_id=assistant.id,
                thread_id=conversation.id,
                trace_id=trace_id[:64] if trace_id else None,
                status=AgentRunStatus.RUNNING.value,
                graph_version=RAG_GRAPH_VERSION,
                detail={
                    "response_mode": "sse",
                    "operation": "regenerate",
                },
                started_at=started_at,
            )
        )
        conversation.updated_at = started_at
        await self._session.commit()
        return StreamingRun(
            conversation_id=conversation.id,
            thread_id=conversation.id,
            question=user_message.content,
            message_id=assistant.id,
            run_id=run.id,
            started_at=started_at,
        )

    async def execute_streaming_run(
        self,
        streaming_run: StreamingRun,
    ) -> AsyncIterator[ChatAnswerStreamEvent]:
        """执行已持久化运行；可安全放入与 HTTP 请求解耦的后台任务。"""

        completed = False
        generation_started = False
        finalizing_started = False
        last_stage: str = "understanding"
        try:
            yield ChatStreamStatus("understanding")
            async for event in self._answer_service.stream(
                question=streaming_run.question,
                thread_id=streaming_run.thread_id,
            ):
                if isinstance(event, RagAnswerStage):
                    if event.stage == last_stage:
                        continue
                    if event.stage == "generating":
                        generation_started = True
                    if event.stage == "finalizing":
                        finalizing_started = True
                    last_stage = event.stage
                    yield ChatStreamStatus(event.stage)
                    continue
                if isinstance(event, RagAnswerDelta):
                    if not generation_started:
                        generation_started = True
                        last_stage = "generating"
                        yield ChatStreamStatus("generating")
                    yield ChatStreamDelta(event.text)
                    continue
                if not isinstance(event, RagAnswerCompleted):
                    raise RuntimeError("unsupported RAG stream event")
                if not finalizing_started:
                    yield ChatStreamStatus("finalizing")
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
                    error_code="user_cancelled",
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
    ) -> StreamingRun:
        await self._prepare()
        conversation = await self._owned_conversation(conversation_id, for_update=True)
        if conversation.status != ConversationStatus.ACTIVE.value:
            raise BusinessRuleError("only active conversations can receive messages")
        await self._ensure_no_running_run(conversation.id)

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
                detail={
                    "response_mode": "sse",
                    "operation": "answer",
                },
                started_at=started_at,
            )
        )
        if conversation.title == DEFAULT_CONVERSATION_TITLE:
            conversation.title = _automatic_title(normalized_question)
        conversation.updated_at = started_at
        await self._session.commit()
        return StreamingRun(
            conversation_id=conversation.id,
            thread_id=conversation.id,
            question=normalized_question,
            message_id=assistant_message.id,
            run_id=run.id,
            started_at=started_at,
        )

    async def _persist_streamed_answer(
        self,
        *,
        streaming_run: StreamingRun,
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
        evidence = await self._persist_finance_evidence(
            run_id=run.id,
            message_id=assistant.id,
            results=result.finance_results,
        )
        run.status = AgentRunStatus.COMPLETED.value
        run.latency_ms = result.latency_ms
        run.completed_at = completed_at
        run.detail = {
            "response_mode": "sse",
            "intent": result.plan.intent if result.plan is not None else "knowledge",
            "planner_mode": _planner_mode(result),
            "route_reason": result.plan.route_reason if result.plan is not None else None,
            "planner_confidence": (result.plan.confidence if result.plan is not None else None),
            "retrieval_source": (
                "hybrid" if result.retrieval.knowledge_base_ids else "not_requested"
            ),
            "retrieval_result_count": len(result.retrieval.items),
            "citation_count": len(citations),
            "embedding_model": result.retrieval.embedding_model,
            "chat_model": result.completion.model if result.completion else None,
            "chat_request_id": (result.completion.request_id if result.completion else None),
            "finish_reason": (
                result.completion.finish_reason if result.completion else "no_context"
            ),
            "checkpoint_id": result.checkpoint_id,
            "checkpoint_namespace": "",
            "data_as_of": (
                result.data_as_of.isoformat() if result.data_as_of is not None else None
            ),
            "finance_tool_count": len(result.finance_results),
            "finance_tool_statuses": [
                tool_result.status.value for tool_result in result.finance_results
            ],
            "risk_policy": (result.plan.risk_policy if result.plan is not None else "standard"),
            "risk_notice": _risk_notice(result),
        }
        await self._session.commit()
        return PersistedAnswer(
            message=assistant,
            citations=citations,
            run=run,
            evidence=evidence,
            data_as_of=result.data_as_of,
            risk_notice=_risk_notice(result),
        )

    async def _persist_finance_evidence(
        self,
        *,
        run_id: UUID,
        message_id: UUID,
        results: tuple[object, ...],
    ) -> list[MessageEvidence]:
        """独立持久化工具审计，并将成功结果关联为消息财务证据。"""

        from app.agents.tools.finance import FinanceToolResult, FinanceToolStatus

        typed_results = [item for item in results if isinstance(item, FinanceToolResult)]
        tool_calls: list[AgentToolCall] = []
        records = []
        for result in typed_results:
            record = build_finance_persistence_record(result)
            records.append(record)
            tool_calls.append(
                AgentToolCall(
                    user_id=self._user_id,
                    run_id=run_id,
                    call_id=result.call_id,
                    tool_name=result.name.value,
                    arguments=record.arguments,
                    status=result.status.value,
                    duration_ms=result.duration_ms,
                    data_as_of=result.data_as_of,
                    result_summary=record.result_summary,
                    result_hash=record.result_hash,
                    error_code=result.error.code if result.error is not None else None,
                )
            )
        await self._repository.add_all(tool_calls)
        evidence: list[MessageEvidence] = []
        for result, tool_call, record in zip(typed_results, tool_calls, records, strict=True):
            if result.status != FinanceToolStatus.SUCCEEDED or result.data is None:
                continue
            evidence.append(
                MessageEvidence(
                    user_id=self._user_id,
                    message_id=message_id,
                    tool_call_id=tool_call.id,
                    rank=len(evidence) + 1,
                    evidence_type="finance",
                    evidence_snapshot=record.evidence_snapshot,
                )
            )
        await self._repository.add_all(evidence)
        return evidence

    async def _mark_stream_terminal(
        self,
        *,
        streaming_run: StreamingRun,
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

    async def _ensure_no_running_run(self, conversation_id: UUID) -> None:
        running = await self._repository.get_running_agent_run(
            user_id=self._user_id,
            conversation_id=conversation_id,
        )
        if running is not None:
            raise ConflictError("this conversation already has a running answer")

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


def _detail_datetime(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def _detail_text(value: object) -> str | None:
    return value if isinstance(value, str) and value.strip() else None


def _planner_mode(result: RagAnswerResult) -> str:
    if result.plan is None:
        return "rules"
    if result.plan.route_reason == "model_structured_plan":
        return "model"
    if result.plan.route_reason.startswith("model_planner_"):
        return "model_fallback"
    return "rules"


def _risk_notice(result: RagAnswerResult) -> str | None:
    if result.plan is None or result.plan.risk_policy != "high_risk_investment":
        return None
    return HIGH_RISK_INVESTMENT_DISCLAIMER
