"""Registration, login, token lifecycle, and password endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Request, status

from app.api.dependencies import (
    AccessContextDependency,
    AuthServiceDependency,
)
from app.api.schemas.auth import (
    ChangePasswordRequest,
    LoginRequest,
    LogoutRequest,
    MessageResponse,
    RefreshRequest,
    RegisterRequest,
    TokenPairResponse,
    UserResponse,
)
from app.services.auth import IssuedTokenPair, RequestMetadata

router = APIRouter(prefix="/auth", tags=["authentication"])


def _request_metadata(request: Request) -> RequestMetadata:
    client_ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent")
    return RequestMetadata(
        ip=client_ip[:64],
        user_agent=user_agent[:512] if user_agent else None,
    )


def _token_response(pair: IssuedTokenPair) -> TokenPairResponse:
    return TokenPairResponse(
        access_token=pair.access_token,
        refresh_token=pair.refresh_token,
        expires_in=pair.access_expires_in,
        refresh_expires_in=pair.refresh_expires_in,
        must_change_password=pair.must_change_password,
    )


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register(
    payload: RegisterRequest,
    request: Request,
    service: AuthServiceDependency,
) -> UserResponse:
    user = await service.register(
        username=payload.username,
        email=str(payload.email),
        raw_password=payload.password.get_secret_value(),
        request=_request_metadata(request),
    )
    return UserResponse.model_validate(user)


@router.post("/login", response_model=TokenPairResponse)
async def login(
    payload: LoginRequest,
    request: Request,
    service: AuthServiceDependency,
) -> TokenPairResponse:
    _user, pair = await service.login(
        identifier=payload.identifier,
        raw_password=payload.password.get_secret_value(),
        request=_request_metadata(request),
    )
    return _token_response(pair)


@router.post("/refresh", response_model=TokenPairResponse)
async def refresh(
    payload: RefreshRequest,
    request: Request,
    service: AuthServiceDependency,
) -> TokenPairResponse:
    _user, pair = await service.refresh(
        raw_refresh_token=payload.refresh_token.get_secret_value(),
        request=_request_metadata(request),
    )
    return _token_response(pair)


@router.post("/logout", response_model=MessageResponse)
async def logout(
    payload: LogoutRequest,
    request: Request,
    context: AccessContextDependency,
    service: AuthServiceDependency,
) -> MessageResponse:
    await service.logout(
        user=context.user,
        claims=context.claims,
        raw_refresh_token=(
            payload.refresh_token.get_secret_value() if payload.refresh_token is not None else None
        ),
        request=_request_metadata(request),
    )
    return MessageResponse(message="logged out")


@router.post("/change-password", response_model=MessageResponse)
async def change_password(
    payload: ChangePasswordRequest,
    request: Request,
    context: AccessContextDependency,
    service: AuthServiceDependency,
) -> MessageResponse:
    await service.change_password(
        user=context.user,
        claims=context.claims,
        current_password=payload.current_password.get_secret_value(),
        new_password=payload.new_password.get_secret_value(),
        request=_request_metadata(request),
    )
    return MessageResponse(message="password changed; sign in again")
