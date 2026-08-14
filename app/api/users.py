"""Current-user profile endpoint."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Header, Query, Response, status

from app.api.dependencies import (
    AccessContextDependency,
    MemoryServiceDependency,
    UserSettingsServiceDependency,
)
from app.api.schemas.auth import UserResponse
from app.api.schemas.users import (
    FinancialProfileCreate,
    FinancialProfileResponse,
    FinancialProfileUpdate,
    MemoryCreate,
    MemoryListResponse,
    MemoryResponse,
    MemorySettingsResponse,
    MemorySettingsUpdate,
    MemoryUpdate,
    PreferenceResponse,
    PreferenceUpdate,
    ProfileResponse,
    ProfileUpdate,
)
from app.db.models.identity import MemoryCategory, MemoryStatus

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserResponse)
async def get_current_user(context: AccessContextDependency) -> UserResponse:
    return UserResponse.model_validate(context.user)


@router.get("/me/profile", response_model=ProfileResponse)
async def get_profile(service: UserSettingsServiceDependency) -> ProfileResponse:
    return ProfileResponse.model_validate(await service.get_profile())


@router.patch("/me/profile", response_model=ProfileResponse)
async def update_profile(
    payload: ProfileUpdate,
    service: UserSettingsServiceDependency,
) -> ProfileResponse:
    profile = await service.update_profile(
        display_name=payload.display_name,
        fields_set=payload.model_fields_set,
    )
    return ProfileResponse.model_validate(profile)


@router.get("/me/preferences", response_model=PreferenceResponse)
async def get_preferences(service: UserSettingsServiceDependency) -> PreferenceResponse:
    return PreferenceResponse.model_validate(await service.get_preferences())


@router.patch("/me/preferences", response_model=PreferenceResponse)
async def update_preferences(
    payload: PreferenceUpdate,
    service: UserSettingsServiceDependency,
) -> PreferenceResponse:
    preferences = await service.update_preferences(
        values=payload.model_dump(exclude_unset=True),
        fields_set=payload.model_fields_set,
    )
    return PreferenceResponse.model_validate(preferences)


@router.post(
    "/me/financial-profile",
    response_model=FinancialProfileResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_financial_profile(
    payload: FinancialProfileCreate,
    service: UserSettingsServiceDependency,
) -> FinancialProfileResponse:
    profile = await service.create_financial_profile(
        values=payload.model_dump(),
        fields_set=payload.model_fields_set,
    )
    return FinancialProfileResponse.model_validate(profile)


@router.get("/me/financial-profile", response_model=FinancialProfileResponse)
async def get_financial_profile(
    service: UserSettingsServiceDependency,
) -> FinancialProfileResponse:
    return FinancialProfileResponse.model_validate(await service.get_financial_profile())


@router.patch("/me/financial-profile", response_model=FinancialProfileResponse)
async def update_financial_profile(
    payload: FinancialProfileUpdate,
    service: UserSettingsServiceDependency,
) -> FinancialProfileResponse:
    profile = await service.update_financial_profile(
        values=payload.model_dump(exclude_unset=True),
        fields_set=payload.model_fields_set,
    )
    return FinancialProfileResponse.model_validate(profile)


@router.delete("/me/financial-profile", status_code=status.HTTP_204_NO_CONTENT)
async def delete_financial_profile(service: UserSettingsServiceDependency) -> Response:
    await service.delete_financial_profile()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me/memory-settings", response_model=MemorySettingsResponse)
async def get_memory_settings(service: MemoryServiceDependency) -> MemorySettingsResponse:
    return MemorySettingsResponse.model_validate(await service.get_settings())


@router.patch("/me/memory-settings", response_model=MemorySettingsResponse)
async def update_memory_settings(
    payload: MemorySettingsUpdate,
    service: MemoryServiceDependency,
) -> MemorySettingsResponse:
    settings = await service.update_settings(
        values=payload.model_dump(exclude_unset=True),
        fields_set=payload.model_fields_set,
    )
    return MemorySettingsResponse.model_validate(settings)


@router.get("/me/memories", response_model=MemoryListResponse)
async def list_memories(
    service: MemoryServiceDependency,
    category: MemoryCategory | None = None,
    memory_status: MemoryStatus | None = Query(default=None, alias="status"),
    search: str | None = Query(default=None, min_length=1, max_length=100),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
) -> MemoryListResponse:
    result = await service.list_memories(
        category=category,
        status=memory_status,
        search=search,
        page=page,
        page_size=page_size,
    )
    return MemoryListResponse(
        items=[MemoryResponse.model_validate(item) for item in result.items],
        total=result.total,
        page=result.page,
        page_size=result.page_size,
    )


@router.post(
    "/me/memories",
    response_model=MemoryResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_memory(
    payload: MemoryCreate,
    service: MemoryServiceDependency,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=1, max_length=128),
) -> MemoryResponse:
    memory = await service.create_memory(
        category=payload.category,
        title=payload.title,
        content=payload.content,
        idempotency_key=idempotency_key,
    )
    return MemoryResponse.model_validate(memory)


@router.get("/me/memories/{memory_id}", response_model=MemoryResponse)
async def get_memory(memory_id: UUID, service: MemoryServiceDependency) -> MemoryResponse:
    return MemoryResponse.model_validate(await service.get_memory(memory_id))


@router.patch("/me/memories/{memory_id}", response_model=MemoryResponse)
async def update_memory(
    memory_id: UUID,
    payload: MemoryUpdate,
    service: MemoryServiceDependency,
) -> MemoryResponse:
    memory = await service.update_memory(
        memory_id,
        values=payload.model_dump(exclude_unset=True),
        fields_set=payload.model_fields_set,
    )
    return MemoryResponse.model_validate(memory)


@router.delete("/me/memories/{memory_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_memory(memory_id: UUID, service: MemoryServiceDependency) -> Response:
    await service.delete_memory(memory_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
