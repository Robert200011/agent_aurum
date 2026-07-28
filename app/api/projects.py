"""Administrator Agent-project management endpoints."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Query, Response, status

from app.api.dependencies import AdminContextDependency, RagAdminServiceDependency
from app.api.schemas.rag import (
    ProjectCreate,
    ProjectListResponse,
    ProjectResponse,
    ProjectUpdate,
)

router = APIRouter(prefix="/admin/projects", tags=["admin-projects"])


@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def create_project(
    payload: ProjectCreate,
    service: RagAdminServiceDependency,
    _admin: AdminContextDependency,
) -> ProjectResponse:
    project = await service.create_project(name=payload.name, description=payload.description)
    return ProjectResponse.model_validate(project)


@router.get("", response_model=ProjectListResponse)
async def list_projects(
    service: RagAdminServiceDependency,
    _admin: AdminContextDependency,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
) -> ProjectListResponse:
    result = await service.list_projects(page=page, page_size=page_size)
    return ProjectListResponse(
        items=[ProjectResponse.model_validate(item) for item in result.items],
        total=result.total,
        page=result.page,
        page_size=result.page_size,
    )


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(
    project_id: UUID,
    service: RagAdminServiceDependency,
    _admin: AdminContextDependency,
) -> ProjectResponse:
    return ProjectResponse.model_validate(await service.get_project(project_id))


@router.patch("/{project_id}", response_model=ProjectResponse)
async def update_project(
    project_id: UUID,
    payload: ProjectUpdate,
    service: RagAdminServiceDependency,
    _admin: AdminContextDependency,
) -> ProjectResponse:
    project = await service.update_project(
        project_id,
        name=payload.name,
        description=payload.description,
        status=payload.status,
        fields_set=set(payload.model_fields_set),
    )
    return ProjectResponse.model_validate(project)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    project_id: UUID,
    service: RagAdminServiceDependency,
    _admin: AdminContextDependency,
) -> Response:
    await service.delete_project(project_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
