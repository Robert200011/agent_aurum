"""Current-user profile endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Response, status

from app.api.dependencies import AccessContextDependency, UserSettingsServiceDependency
from app.api.schemas.auth import UserResponse
from app.api.schemas.users import (
    FinancialProfileCreate,
    FinancialProfileResponse,
    FinancialProfileUpdate,
    PreferenceResponse,
    PreferenceUpdate,
    ProfileResponse,
    ProfileUpdate,
)

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
