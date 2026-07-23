"""Current-user profile endpoint."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.dependencies import AccessContextDependency
from app.api.schemas.auth import UserResponse

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserResponse)
async def get_current_user(context: AccessContextDependency) -> UserResponse:
    return UserResponse.model_validate(context.user)
