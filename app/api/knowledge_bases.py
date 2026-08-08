"""Personal knowledge-base management and search-preview endpoints."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Query, Response, status

from app.api.dependencies import (
    PersonalKnowledgeServiceDependency,
    RagRetrievalServiceDependency,
)
from app.api.schemas.rag import (
    KnowledgeBaseCreate,
    KnowledgeBaseListResponse,
    KnowledgeBaseResponse,
    KnowledgeBaseUpdate,
    RetrievalRequest,
    RetrievalResponse,
)

router = APIRouter(prefix="/knowledge-bases", tags=["personal-knowledge"])


@router.post("", response_model=KnowledgeBaseResponse, status_code=status.HTTP_201_CREATED)
async def create_knowledge_base(
    payload: KnowledgeBaseCreate,
    service: PersonalKnowledgeServiceDependency,
) -> KnowledgeBaseResponse:
    knowledge_base = await service.create_knowledge_base(
        name=payload.name,
        description=payload.description,
    )
    return KnowledgeBaseResponse.model_validate(knowledge_base)


@router.get("", response_model=KnowledgeBaseListResponse)
async def list_knowledge_bases(
    service: PersonalKnowledgeServiceDependency,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
) -> KnowledgeBaseListResponse:
    result = await service.list_knowledge_bases(page=page, page_size=page_size)
    return KnowledgeBaseListResponse(
        items=[KnowledgeBaseResponse.model_validate(item) for item in result.items],
        total=result.total,
        page=result.page,
        page_size=result.page_size,
    )


@router.get("/{knowledge_base_id}", response_model=KnowledgeBaseResponse)
async def get_knowledge_base(
    knowledge_base_id: UUID,
    service: PersonalKnowledgeServiceDependency,
) -> KnowledgeBaseResponse:
    return KnowledgeBaseResponse.model_validate(await service.get_knowledge_base(knowledge_base_id))


@router.post("/{knowledge_base_id}/search-preview", response_model=RetrievalResponse)
async def preview_knowledge_base_search(
    knowledge_base_id: UUID,
    payload: RetrievalRequest,
    service: RagRetrievalServiceDependency,
) -> RetrievalResponse:
    result = await service.retrieve(
        knowledge_base_id=knowledge_base_id,
        query=payload.query,
        limit=payload.limit,
        min_score=payload.min_score,
    )
    return RetrievalResponse.model_validate(result)


@router.patch("/{knowledge_base_id}", response_model=KnowledgeBaseResponse)
async def update_knowledge_base(
    knowledge_base_id: UUID,
    payload: KnowledgeBaseUpdate,
    service: PersonalKnowledgeServiceDependency,
) -> KnowledgeBaseResponse:
    knowledge_base = await service.update_knowledge_base(
        knowledge_base_id,
        name=payload.name,
        description=payload.description,
        status=payload.status,
        search_enabled=payload.search_enabled,
        fields_set=set(payload.model_fields_set),
    )
    return KnowledgeBaseResponse.model_validate(knowledge_base)


@router.delete("/{knowledge_base_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_knowledge_base(
    knowledge_base_id: UUID,
    service: PersonalKnowledgeServiceDependency,
) -> Response:
    await service.delete_knowledge_base(knowledge_base_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
