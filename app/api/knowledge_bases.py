"""Administrator knowledge-base management and explicit-sharing endpoints."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Query, Response, status

from app.api.dependencies import (
    AdminContextDependency,
    RagAdminServiceDependency,
    RagRetrievalServiceDependency,
)
from app.api.schemas.rag import (
    KnowledgeBaseCreate,
    KnowledgeBaseListResponse,
    KnowledgeBaseResponse,
    KnowledgeBaseUpdate,
    ProjectKnowledgeBaseCreate,
    ProjectKnowledgeBaseResponse,
    RetrievalRequest,
    RetrievalResponse,
)

router = APIRouter(prefix="/admin/knowledge-bases", tags=["admin-knowledge-bases"])


@router.post("", response_model=KnowledgeBaseResponse, status_code=status.HTTP_201_CREATED)
async def create_knowledge_base(
    payload: KnowledgeBaseCreate,
    service: RagAdminServiceDependency,
    _admin: AdminContextDependency,
) -> KnowledgeBaseResponse:
    knowledge_base = await service.create_knowledge_base(
        project_id=payload.project_id,
        name=payload.name,
        description=payload.description,
    )
    return KnowledgeBaseResponse.model_validate(knowledge_base)


@router.get("", response_model=KnowledgeBaseListResponse)
async def list_knowledge_bases(
    service: RagAdminServiceDependency,
    _admin: AdminContextDependency,
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
    service: RagAdminServiceDependency,
    _admin: AdminContextDependency,
) -> KnowledgeBaseResponse:
    return KnowledgeBaseResponse.model_validate(await service.get_knowledge_base(knowledge_base_id))


@router.post("/{knowledge_base_id}/retrieve", response_model=RetrievalResponse)
async def retrieve_knowledge_base(
    knowledge_base_id: UUID,
    payload: RetrievalRequest,
    service: RagRetrievalServiceDependency,
    _admin: AdminContextDependency,
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
    service: RagAdminServiceDependency,
    _admin: AdminContextDependency,
) -> KnowledgeBaseResponse:
    knowledge_base = await service.update_knowledge_base(
        knowledge_base_id,
        name=payload.name,
        description=payload.description,
        fields_set=set(payload.model_fields_set),
    )
    return KnowledgeBaseResponse.model_validate(knowledge_base)


@router.post("/{knowledge_base_id}/publish", response_model=KnowledgeBaseResponse)
async def publish_knowledge_base(
    knowledge_base_id: UUID,
    service: RagAdminServiceDependency,
    _admin: AdminContextDependency,
) -> KnowledgeBaseResponse:
    return KnowledgeBaseResponse.model_validate(
        await service.publish_knowledge_base(knowledge_base_id)
    )


@router.post("/{knowledge_base_id}/disable", response_model=KnowledgeBaseResponse)
async def disable_knowledge_base(
    knowledge_base_id: UUID,
    service: RagAdminServiceDependency,
    _admin: AdminContextDependency,
) -> KnowledgeBaseResponse:
    return KnowledgeBaseResponse.model_validate(
        await service.disable_knowledge_base(knowledge_base_id)
    )


@router.delete("/{knowledge_base_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_knowledge_base(
    knowledge_base_id: UUID,
    service: RagAdminServiceDependency,
    _admin: AdminContextDependency,
) -> Response:
    await service.delete_knowledge_base(knowledge_base_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{knowledge_base_id}/projects", response_model=list[ProjectKnowledgeBaseResponse])
async def list_bound_projects(
    knowledge_base_id: UUID,
    service: RagAdminServiceDependency,
    _admin: AdminContextDependency,
) -> list[ProjectKnowledgeBaseResponse]:
    bindings = await service.list_knowledge_base_bindings(knowledge_base_id)
    return [ProjectKnowledgeBaseResponse.model_validate(binding) for binding in bindings]


@router.post(
    "/{knowledge_base_id}/projects",
    response_model=ProjectKnowledgeBaseResponse,
    status_code=status.HTTP_201_CREATED,
)
async def bind_knowledge_base(
    knowledge_base_id: UUID,
    payload: ProjectKnowledgeBaseCreate,
    service: RagAdminServiceDependency,
    _admin: AdminContextDependency,
) -> ProjectKnowledgeBaseResponse:
    binding = await service.bind_knowledge_base(
        knowledge_base_id=knowledge_base_id,
        project_id=payload.project_id,
    )
    return ProjectKnowledgeBaseResponse.model_validate(binding)


@router.delete("/{knowledge_base_id}/projects/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def unbind_knowledge_base(
    knowledge_base_id: UUID,
    project_id: UUID,
    service: RagAdminServiceDependency,
    _admin: AdminContextDependency,
) -> Response:
    await service.unbind_knowledge_base(
        knowledge_base_id=knowledge_base_id,
        project_id=project_id,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
