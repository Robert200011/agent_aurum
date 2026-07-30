"""普通登录用户的会话、非流式与 SSE 基础 RAG 问答 API。"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from uuid import UUID

from fastapi import APIRouter, Query, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.api.dependencies import ChatServiceDependency
from app.api.schemas.chat import (
    AvailableProjectListResponse,
    AvailableProjectResponse,
    ConversationCreate,
    ConversationDetailResponse,
    ConversationListResponse,
    ConversationResponse,
    ConversationUpdate,
    MessageCitationResponse,
    MessageResponse,
    QuestionCreate,
    StreamDeltaResponse,
    StreamErrorResponse,
    StreamStartedResponse,
    StructuredAnswerResponse,
)
from app.db.models.chat import Message, MessageCitation
from app.errors import ApplicationError
from app.services.chat import (
    ChatStreamCompleted,
    ChatStreamDelta,
    ChatStreamStarted,
    PersistedAnswer,
)

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
) -> ConversationListResponse:
    result = await service.list_conversations(page=page, page_size=page_size)
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
) -> StreamingResponse:
    """通过 POST SSE 逐段发送回答，并在 complete 事件附带可信引用。"""

    return StreamingResponse(
        _answer_event_stream(
            conversation_id=conversation_id,
            question=payload.question,
            request=request,
            service=service,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
        },
    )


async def _answer_event_stream(
    *,
    conversation_id: UUID,
    question: str,
    request: Request,
    service: ChatServiceDependency,
) -> AsyncIterator[str]:
    sequence = 0
    try:
        async for event in service.stream_answer(
            conversation_id=conversation_id,
            question=question,
            trace_id=_request_id(request),
        ):
            sequence += 1
            if isinstance(event, ChatStreamStarted):
                yield _sse(
                    event="start",
                    event_id=sequence,
                    payload=StreamStartedResponse(
                        message_id=event.message_id,
                        run_id=event.run_id,
                    ),
                )
            elif isinstance(event, ChatStreamDelta):
                yield _sse(
                    event="delta",
                    event_id=sequence,
                    payload=StreamDeltaResponse(delta=event.text),
                )
            elif isinstance(event, ChatStreamCompleted):
                yield _sse(
                    event="complete",
                    event_id=sequence,
                    payload=_structured_answer_response(event.answer),
                )
            else:
                raise RuntimeError("unsupported chat stream event")
    except asyncio.CancelledError:
        raise
    except ApplicationError as exc:
        sequence += 1
        yield _sse(
            event="error",
            event_id=sequence,
            payload=StreamErrorResponse(
                code=exc.code,
                message=exc.message,
                request_id=_request_id(request),
            ),
        )
    except Exception:
        logger.exception("unhandled streaming answer error")
        sequence += 1
        yield _sse(
            event="error",
            event_id=sequence,
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
) -> MessageResponse:
    response = MessageResponse.model_validate(message)
    return response.model_copy(
        update={
            "citations": [_citation_response(citation) for citation in citations],
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


def _request_id(request: Request) -> str | None:
    request_id = getattr(request.state, "request_id", None)
    return request_id if isinstance(request_id, str) else None
