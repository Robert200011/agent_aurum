"""普通登录用户的会话、非流式与 SSE 基础 RAG 问答 API。"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Query, Request, Response, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.api.dependencies import ChatRunCoordinatorDependency, ChatServiceDependency
from app.api.schemas.chat import (
    AgentRunResponse,
    AvailableProjectListResponse,
    AvailableProjectResponse,
    ConversationCreate,
    ConversationDetailResponse,
    ConversationListResponse,
    ConversationResponse,
    ConversationUpdate,
    MessageCitationResponse,
    MessageEvidenceResponse,
    MessageResponse,
    QuestionCreate,
    RunCancellationResponse,
    StreamDeltaResponse,
    StreamErrorResponse,
    StreamStartedResponse,
    StreamStatusResponse,
    StructuredAnswerResponse,
)
from app.db.models.chat import AgentRun, Message, MessageCitation, MessageEvidence
from app.errors import ApplicationError, ConflictError
from app.services.chat import (
    ChatStreamCompleted,
    ChatStreamDelta,
    ChatStreamStarted,
    ChatStreamStatus,
    PersistedAnswer,
)
from app.services.chat_runs import BufferedChatEvent, ChatRunError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/conversations", tags=["conversations"])
project_router = APIRouter(prefix="/chat", tags=["chat"])


@project_router.get("/projects", response_model=AvailableProjectListResponse)
async def list_available_projects(
    service: ChatServiceDependency,
) -> AvailableProjectListResponse:
    projects = await service.list_available_projects()
    return AvailableProjectListResponse(
        items=[AvailableProjectResponse.model_validate(project) for project in projects]
    )


@router.post("", response_model=ConversationResponse, status_code=status.HTTP_201_CREATED)
async def create_conversation(
    payload: ConversationCreate,
    service: ChatServiceDependency,
) -> ConversationResponse:
    conversation = await service.create_conversation(
        project_id=payload.project_id,
        title=payload.title,
    )
    return ConversationResponse.model_validate(conversation)


@router.get("", response_model=ConversationListResponse)
async def list_conversations(
    service: ChatServiceDependency,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    search: str | None = Query(default=None, min_length=1, max_length=100),
) -> ConversationListResponse:
    result = await service.list_conversations(
        page=page,
        page_size=page_size,
        search=search,
    )
    return ConversationListResponse(
        items=[ConversationResponse.model_validate(item) for item in result.items],
        total=result.total,
        page=result.page,
        page_size=result.page_size,
    )


@router.get("/{conversation_id}", response_model=ConversationDetailResponse)
async def get_conversation(
    conversation_id: UUID,
    service: ChatServiceDependency,
) -> ConversationDetailResponse:
    detail = await service.get_conversation(conversation_id)
    return ConversationDetailResponse(
        **ConversationResponse.model_validate(detail.conversation).model_dump(),
        messages=[
            _message_response(
                message,
                detail.citations_by_message.get(message.id, []),
                detail.evidence_by_message.get(message.id, []),
                detail.runs_by_message.get(message.id),
            )
            for message in detail.messages
        ],
    )


@router.patch("/{conversation_id}", response_model=ConversationResponse)
async def update_conversation(
    conversation_id: UUID,
    payload: ConversationUpdate,
    service: ChatServiceDependency,
) -> ConversationResponse:
    conversation = await service.update_conversation(
        conversation_id,
        title=payload.title,
        status=payload.status,
        fields_set=set(payload.model_fields_set),
    )
    return ConversationResponse.model_validate(conversation)


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(
    conversation_id: UUID,
    service: ChatServiceDependency,
    coordinator: ChatRunCoordinatorDependency,
) -> Response:
    await service.delete_conversation(conversation_id)
    try:
        await coordinator.delete_thread(conversation_id)
    except Exception:
        logger.exception(
            "unable to delete conversation checkpoint thread",
            extra={"conversation_id": conversation_id},
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/{conversation_id}/runs/latest",
    response_model=AgentRunResponse | None,
)
async def get_latest_conversation_run(
    conversation_id: UUID,
    service: ChatServiceDependency,
) -> AgentRunResponse | None:
    run = await service.get_latest_run(conversation_id)
    return _agent_run_response(run) if run is not None else None


@router.post(
    "/{conversation_id}/messages",
    response_model=StructuredAnswerResponse,
    status_code=status.HTTP_201_CREATED,
)
async def answer_conversation(
    conversation_id: UUID,
    payload: QuestionCreate,
    request: Request,
    service: ChatServiceDependency,
) -> StructuredAnswerResponse:
    persisted = await service.answer(
        conversation_id=conversation_id,
        question=payload.question,
        trace_id=_request_id(request),
    )
    return _structured_answer_response(persisted)


@router.post("/{conversation_id}/messages/stream")
async def stream_answer_conversation(
    conversation_id: UUID,
    payload: QuestionCreate,
    request: Request,
    service: ChatServiceDependency,
    coordinator: ChatRunCoordinatorDependency,
) -> StreamingResponse:
    """启动独立生成任务，并通过 POST SSE 订阅其可重放事件。"""

    run = await service.start_streaming_run(
        conversation_id=conversation_id,
        question=payload.question,
        trace_id=_request_id(request),
    )
    coordinator.start(user_id=service.user_id, run=run)
    return StreamingResponse(
        _coordinated_event_stream(
            conversation_id=conversation_id,
            run_id=run.run_id,
            after_sequence=0,
            request=request,
            service=service,
            coordinator=coordinator,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/{conversation_id}/messages/{message_id}/regenerate/stream")
async def regenerate_answer(
    conversation_id: UUID,
    message_id: UUID,
    request: Request,
    service: ChatServiceDependency,
    coordinator: ChatRunCoordinatorDependency,
) -> StreamingResponse:
    run = await service.regenerate_streaming_run(
        conversation_id=conversation_id,
        message_id=message_id,
        trace_id=_request_id(request),
    )
    coordinator.start(user_id=service.user_id, run=run)
    return StreamingResponse(
        _coordinated_event_stream(
            conversation_id=conversation_id,
            run_id=run.run_id,
            after_sequence=0,
            request=request,
            service=service,
            coordinator=coordinator,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/{conversation_id}/runs/{run_id}/stream")
async def resume_answer_stream(
    conversation_id: UUID,
    run_id: UUID,
    request: Request,
    service: ChatServiceDependency,
    coordinator: ChatRunCoordinatorDependency,
    after: int = Query(default=0, ge=0),
) -> StreamingResponse:
    await service.get_run(conversation_id, run_id)
    return StreamingResponse(
        _coordinated_event_stream(
            conversation_id=conversation_id,
            run_id=run_id,
            after_sequence=after,
            request=request,
            service=service,
            coordinator=coordinator,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
        },
    )


@router.post(
    "/{conversation_id}/runs/{run_id}/cancel",
    response_model=RunCancellationResponse,
)
async def cancel_answer_run(
    conversation_id: UUID,
    run_id: UUID,
    service: ChatServiceDependency,
    coordinator: ChatRunCoordinatorDependency,
) -> RunCancellationResponse:
    run = await service.get_run(conversation_id, run_id)
    if run.status not in {"queued", "running"}:
        raise ConflictError("agent run is already in a terminal state")
    cancelled = await coordinator.cancel(run_id)
    if not cancelled:
        await service.cancel_run(conversation_id, run_id)
    return RunCancellationResponse(run_id=run_id, status="cancelled")


async def _coordinated_event_stream(
    *,
    conversation_id: UUID,
    run_id: UUID,
    after_sequence: int,
    request: Request,
    service: ChatServiceDependency,
    coordinator: ChatRunCoordinatorDependency,
) -> AsyncIterator[str]:
    last_sequence = after_sequence
    try:
        if not coordinator.has_run(run_id):
            persisted = await service.persisted_answer_for_run(conversation_id, run_id)
            if persisted is not None:
                yield _sse(
                    event="complete",
                    event_id=after_sequence + 1,
                    payload=_structured_answer_response(persisted),
                )
                return
            run = await service.get_run(conversation_id, run_id)
            orphaned = run.status in {"queued", "running"}
            if orphaned:
                run = await service.cancel_run(conversation_id, run_id)
            yield _sse(
                event="error",
                event_id=after_sequence + 1,
                payload=StreamErrorResponse(
                    code=(
                        "run_recovery_unavailable"
                        if orphaned
                        else run.error_code or "run_recovery_unavailable"
                    ),
                    message=(
                        "the previous server process ended; please retry the answer"
                        if orphaned
                        else "answer generation was cancelled"
                        if run.status == "cancelled"
                        else "answer generation could not be recovered"
                    ),
                    request_id=_request_id(request),
                ),
            )
            return

        async for coordinated in coordinator.subscribe(
            run_id,
            after_sequence=after_sequence,
        ):
            if isinstance(coordinated, ChatRunError):
                last_sequence += 1
                yield _sse(
                    event="error",
                    event_id=last_sequence,
                    payload=StreamErrorResponse(
                        code=coordinated.code,
                        message=coordinated.message,
                        request_id=_request_id(request),
                    ),
                )
                return
            if not isinstance(coordinated, BufferedChatEvent):
                raise RuntimeError("unsupported coordinated chat event")
            last_sequence = coordinated.sequence
            event = coordinated.event
            if isinstance(event, ChatStreamStarted):
                payload: BaseModel = StreamStartedResponse(
                    message_id=event.message_id,
                    run_id=event.run_id,
                )
                event_name = "start"
            elif isinstance(event, ChatStreamStatus):
                payload = StreamStatusResponse(stage=event.stage)
                event_name = "status"
            elif isinstance(event, ChatStreamDelta):
                payload = StreamDeltaResponse(delta=event.text)
                event_name = "delta"
            elif isinstance(event, ChatStreamCompleted):
                payload = _structured_answer_response(event.answer)
                event_name = "complete"
            else:
                raise RuntimeError("unsupported chat stream event")
            yield _sse(
                event=event_name,
                event_id=coordinated.sequence,
                payload=payload,
            )
    except asyncio.CancelledError:
        # HTTP 订阅断开不取消后台模型任务；显式停止使用 cancel 端点。
        raise
    except ApplicationError as exc:
        last_sequence += 1
        yield _sse(
            event="error",
            event_id=last_sequence,
            payload=StreamErrorResponse(
                code=exc.code,
                message=exc.message,
                request_id=_request_id(request),
            ),
        )
    except Exception:
        logger.exception("unhandled streaming answer error")
        last_sequence += 1
        yield _sse(
            event="error",
            event_id=last_sequence,
            payload=StreamErrorResponse(
                code="internal_error",
                message="an internal error occurred",
                request_id=_request_id(request),
            ),
        )


def _structured_answer_response(persisted: PersistedAnswer) -> StructuredAnswerResponse:
    return StructuredAnswerResponse(
        message_id=persisted.message.id,
        answer=persisted.message.content,
        citations=[_citation_response(citation) for citation in persisted.citations],
        evidence=[_evidence_response(item) for item in persisted.evidence],
        data_as_of=persisted.data_as_of,
        risk_notice=persisted.risk_notice,
    )


def _agent_run_response(run: AgentRun) -> AgentRunResponse:
    response = AgentRunResponse.model_validate(run)
    count = run.detail.get("finance_tool_count")
    return response.model_copy(
        update={
            "finance_tool_count": count if isinstance(count, int) and count >= 0 else 0,
            "data_as_of": _run_detail_datetime(run, "data_as_of"),
            "risk_notice": _run_detail_text(run, "risk_notice"),
        }
    )


def _sse(*, event: str, event_id: int, payload: BaseModel) -> str:
    data = json.dumps(
        payload.model_dump(mode="json"),
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return f"id: {event_id}\nevent: {event}\ndata: {data}\n\n"


def _message_response(
    message: Message,
    citations: list[MessageCitation],
    evidence: list[MessageEvidence],
    run: AgentRun | None,
) -> MessageResponse:
    response = MessageResponse.model_validate(message)
    return response.model_copy(
        update={
            "citations": [_citation_response(citation) for citation in citations],
            "evidence": [_evidence_response(item) for item in evidence],
            "data_as_of": (
                _run_detail_datetime(run, "data_as_of") if run is not None else None
            ),
            "risk_notice": (
                _run_detail_text(run, "risk_notice") if run is not None else None
            ),
        }
    )


def _citation_response(citation: MessageCitation) -> MessageCitationResponse:
    return MessageCitationResponse.model_validate(
        citation.source_snapshot
        | {
            "citation_id": citation.rank,
            "quote": citation.quote_snapshot,
            "score": citation.score,
        }
    )


def _evidence_response(evidence: MessageEvidence) -> MessageEvidenceResponse:
    return MessageEvidenceResponse.model_validate(
        evidence.evidence_snapshot
        | {
            "evidence_id": evidence.id,
            "tool_call_id": evidence.tool_call_id,
            "rank": evidence.rank,
        }
    )


def _run_detail_datetime(run: AgentRun, key: str) -> datetime | None:
    value = run.detail.get(key)
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def _run_detail_text(run: AgentRun, key: str) -> str | None:
    value = run.detail.get(key)
    return value if isinstance(value, str) and value.strip() else None


def _request_id(request: Request) -> str | None:
    request_id = getattr(request.state, "request_id", None)
    return request_id if isinstance(request_id, str) else None
