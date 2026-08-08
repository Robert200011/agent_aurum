"""Registration, login, token lifecycle, and password endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Request, Response, status

from app.api.dependencies import (
    AccessContextDependency,
    AuthServiceDependency,
    SettingsDependency,
)
from app.api.schemas.auth import (
    ChangePasswordRequest,
    LoginRequest,
    MessageResponse,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)
from app.config import Settings
from app.errors import AuthenticationError, AuthorizationError
from app.services.auth import IssuedTokenPair, RequestMetadata

router = APIRouter(prefix="/auth", tags=["authentication"])


def _request_metadata(request: Request) -> RequestMetadata:
    client_ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent")
    return RequestMetadata(
        ip=client_ip[:64],
        user_agent=user_agent[:512] if user_agent else None,
    )


def _token_response(pair: IssuedTokenPair) -> TokenResponse:
    return TokenResponse(
        access_token=pair.access_token,
        expires_in=pair.access_expires_in,
        refresh_expires_in=pair.refresh_expires_in,
    )


def _set_refresh_cookie(
    response: Response,
    pair: IssuedTokenPair,
    settings: Settings,
) -> None:
    """仅通过受限的 HttpOnly Cookie 向浏览器下发刷新令牌。"""

    response.set_cookie(
        key=settings.refresh_token_cookie_name,
        value=pair.refresh_token,
        max_age=pair.refresh_expires_in,
        path=settings.refresh_token_cookie_path,
        secure=settings.refresh_token_cookie_secure,
        httponly=True,
        samesite=settings.refresh_token_cookie_samesite,
    )


def _delete_refresh_cookie(response: Response, settings: Settings) -> None:
    """使用与写入时一致的属性删除浏览器中的刷新令牌 Cookie。"""

    response.delete_cookie(
        key=settings.refresh_token_cookie_name,
        path=settings.refresh_token_cookie_path,
        secure=settings.refresh_token_cookie_secure,
        httponly=True,
        samesite=settings.refresh_token_cookie_samesite,
    )


def _refresh_token_from_cookie(request: Request, settings: Settings) -> str:
    raw_refresh_token = request.cookies.get(settings.refresh_token_cookie_name)
    if not raw_refresh_token:
        raise AuthenticationError("refresh token cookie is missing")
    return raw_refresh_token


def _validate_cookie_request_origin(request: Request, settings: Settings) -> None:
    """拒绝浏览器从未授权来源发起自动携带 Cookie 的认证请求。"""

    origin = request.headers.get("origin")
    if origin is not None and origin not in settings.cors_origins:
        raise AuthorizationError("untrusted request origin")


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


@router.post("/login", response_model=TokenResponse)
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    service: AuthServiceDependency,
    settings: SettingsDependency,
) -> TokenResponse:
    _user, pair = await service.login(
        identifier=payload.identifier,
        raw_password=payload.password.get_secret_value(),
        request=_request_metadata(request),
    )
    _set_refresh_cookie(response, pair, settings)
    return _token_response(pair)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    request: Request,
    response: Response,
    service: AuthServiceDependency,
    settings: SettingsDependency,
) -> TokenResponse:
    _validate_cookie_request_origin(request, settings)
    _user, pair = await service.refresh(
        raw_refresh_token=_refresh_token_from_cookie(request, settings),
        request=_request_metadata(request),
    )
    _set_refresh_cookie(response, pair, settings)
    return _token_response(pair)


@router.post("/logout", response_model=MessageResponse)
async def logout(
    request: Request,
    response: Response,
    context: AccessContextDependency,
    service: AuthServiceDependency,
    settings: SettingsDependency,
) -> MessageResponse:
    _validate_cookie_request_origin(request, settings)
    await service.logout(
        user=context.user,
        claims=context.claims,
        raw_refresh_token=request.cookies.get(settings.refresh_token_cookie_name),
        request=_request_metadata(request),
    )
    _delete_refresh_cookie(response, settings)
    return MessageResponse(message="logged out")


@router.post("/change-password", response_model=MessageResponse)
async def change_password(
    payload: ChangePasswordRequest,
    request: Request,
    response: Response,
    context: AccessContextDependency,
    service: AuthServiceDependency,
    settings: SettingsDependency,
) -> MessageResponse:
    await service.change_password(
        user=context.user,
        claims=context.claims,
        current_password=payload.current_password.get_secret_value(),
        new_password=payload.new_password.get_secret_value(),
        request=_request_metadata(request),
    )
    _delete_refresh_cookie(response, settings)
    return MessageResponse(message="password changed; sign in again")
