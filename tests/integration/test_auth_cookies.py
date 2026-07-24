"""刷新令牌 Cookie 的 HTTP 边界测试。"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from pydantic import SecretStr

from app.api.dependencies import get_access_context, get_auth_service
from app.config import Settings, get_settings
from app.errors import RateLimitError
from app.main import create_app
from app.services.auth import IssuedTokenPair


class FakeAuthService:
    """记录认证接口传递的令牌，避免测试依赖数据库和 Redis。"""

    def __init__(self) -> None:
        self.refresh_inputs: list[str] = []
        self.logout_refresh_token: str | None = None

    async def login(self, **kwargs: object) -> tuple[object, IssuedTokenPair]:
        return object(), _token_pair(access_token="access-one", refresh_token="refresh-one")

    async def refresh(self, **kwargs: object) -> tuple[object, IssuedTokenPair]:
        self.refresh_inputs.append(str(kwargs["raw_refresh_token"]))
        return object(), _token_pair(access_token="access-two", refresh_token="refresh-two")

    async def logout(self, **kwargs: object) -> None:
        raw_refresh_token = kwargs["raw_refresh_token"]
        self.logout_refresh_token = (
            str(raw_refresh_token) if raw_refresh_token is not None else None
        )


class RateLimitedAuthService(FakeAuthService):
    async def login(self, **kwargs: object) -> tuple[object, IssuedTokenPair]:
        raise RateLimitError(
            "too many login attempts; try again later",
            retry_after_seconds=17,
        )


def _token_pair(*, access_token: str, refresh_token: str) -> IssuedTokenPair:
    return IssuedTokenPair(
        access_token=access_token,
        refresh_token=refresh_token,
        access_expires_in=900,
        refresh_expires_in=3600,
        must_change_password=False,
    )


def _test_app(
    service: FakeAuthService,
) -> tuple[Any, Settings]:
    settings = Settings(
        environment="test",
        bootstrap_admin=False,
        jwt_secret_key=SecretStr("test-signing-key-with-more-than-32-characters"),
    )
    app = create_app(settings)
    app.state.security_store = object()
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_auth_service] = lambda: service
    app.dependency_overrides[get_access_context] = lambda: SimpleNamespace(
        user=object(),
        claims=object(),
    )
    return app, settings


@pytest.mark.asyncio
async def test_login_and_refresh_rotate_httponly_cookie() -> None:
    service = FakeAuthService()
    app, settings = _test_app(service)
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        login_response = await client.post(
            "/api/v1/auth/login",
            json={"identifier": "demo", "password": "Password123"},
        )
        refresh_response = await client.post(
            "/api/v1/auth/refresh",
            headers={"Origin": "http://localhost:5173"},
        )

    assert login_response.status_code == 200
    assert "refresh_token" not in login_response.json()
    login_cookie = login_response.headers["set-cookie"]
    assert f"{settings.refresh_token_cookie_name}=refresh-one" in login_cookie
    assert "HttpOnly" in login_cookie
    assert "SameSite=lax" in login_cookie
    assert "Path=/api/v1/auth" in login_cookie

    assert refresh_response.status_code == 200
    assert "refresh_token" not in refresh_response.json()
    assert service.refresh_inputs == ["refresh-one"]
    assert f"{settings.refresh_token_cookie_name}=refresh-two" in refresh_response.headers[
        "set-cookie"
    ]


@pytest.mark.asyncio
async def test_refresh_rejects_untrusted_browser_origin() -> None:
    service = FakeAuthService()
    app, settings = _test_app(service)
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        client.cookies.set(
            settings.refresh_token_cookie_name,
            "refresh-one",
            path=settings.refresh_token_cookie_path,
        )
        response = await client.post(
            "/api/v1/auth/refresh",
            headers={"Origin": "https://attacker.example"},
        )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "permission_denied"
    assert service.refresh_inputs == []


@pytest.mark.asyncio
async def test_logout_revokes_cookie_token_and_clears_cookie() -> None:
    service = FakeAuthService()
    app, settings = _test_app(service)
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        client.cookies.set(
            settings.refresh_token_cookie_name,
            "refresh-one",
            path=settings.refresh_token_cookie_path,
        )
        response = await client.post(
            "/api/v1/auth/logout",
            headers={"Origin": "http://localhost:5173"},
        )

    assert response.status_code == 200
    assert service.logout_refresh_token == "refresh-one"
    deletion_cookie = response.headers["set-cookie"]
    assert f"{settings.refresh_token_cookie_name}=" in deletion_cookie
    assert "Max-Age=0" in deletion_cookie
    assert "HttpOnly" in deletion_cookie
    assert "Path=/api/v1/auth" in deletion_cookie


@pytest.mark.asyncio
async def test_login_rate_limit_response_includes_retry_after() -> None:
    service = RateLimitedAuthService()
    app, _settings = _test_app(service)
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/auth/login",
            json={"identifier": "demo", "password": "Password123"},
        )

    assert response.status_code == 429
    assert response.headers["retry-after"] == "17"
    assert response.json()["error"]["code"] == "rate_limit_exceeded"
