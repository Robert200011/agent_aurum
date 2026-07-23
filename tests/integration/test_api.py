"""HTTP boundary smoke tests without external dependencies."""

from __future__ import annotations

import httpx
import pytest
from pydantic import SecretStr

from app.config import Settings
from app.main import create_app


@pytest.mark.asyncio
async def test_liveness_and_security_headers() -> None:
    app = create_app(
        Settings(
            environment="test",
            bootstrap_admin=False,
            jwt_secret_key=SecretStr("test-signing-key-with-more-than-32-characters"),
        )
    )
    app.state.security_store = object()
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["x-request-id"]


@pytest.mark.asyncio
async def test_invalid_registration_uses_stable_error_shape() -> None:
    app = create_app(
        Settings(
            environment="test",
            bootstrap_admin=False,
            jwt_secret_key=SecretStr("test-signing-key-with-more-than-32-characters"),
        )
    )
    app.state.security_store = object()
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/auth/register",
            json={"username": "bad space", "email": "invalid", "password": "short"},
        )

    payload = response.json()
    assert response.status_code == 422
    assert payload["error"]["code"] == "validation_error"
    assert payload["error"]["request_id"]
