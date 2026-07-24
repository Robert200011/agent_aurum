"""Redis 安全状态存储的登录限流测试。"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest
from pydantic import SecretStr
from redis.exceptions import RedisError

from app.config import Settings
from app.errors import RateLimitError, ServiceUnavailableError
from app.providers.identity import RedisSecurityStore, SecurityStore
from app.services.auth import AuthService, RequestMetadata


def _store(redis: Any) -> RedisSecurityStore:
    return RedisSecurityStore(
        redis,
        Settings(
            environment="test",
            jwt_secret_key=SecretStr("test-signing-key-with-more-than-32-characters"),
            login_ip_request_limit=30,
            login_global_request_limit=300,
            login_request_window_seconds=60,
        ),
    )


@pytest.mark.asyncio
async def test_login_guard_consumes_ip_and_global_quotas_atomically() -> None:
    redis = AsyncMock()
    redis.eval.return_value = [0, 0]
    store = _store(redis)

    await store.assert_login_allowed("Demo.User", "203.0.113.8")

    arguments = redis.eval.await_args.args
    assert arguments[1] == 3
    assert arguments[5:] == ("60", "30", "300", "5")
    assert "203.0.113.8" not in arguments[2]
    assert "{login}" in arguments[2]
    assert "{login}" in arguments[3]
    assert "{login}" in arguments[4]


@pytest.mark.asyncio
@pytest.mark.parametrize("decision", [1, 2, 3])
async def test_each_login_guard_rejection_returns_retry_after(decision: int) -> None:
    redis = AsyncMock()
    redis.eval.return_value = [decision, 42]
    store = _store(redis)

    with pytest.raises(RateLimitError) as exc_info:
        await store.assert_login_allowed("demo", "203.0.113.8")

    assert exc_info.value.retry_after_seconds == 42
    assert exc_info.value.code == "rate_limit_exceeded"


@pytest.mark.asyncio
async def test_login_failure_increment_and_expiry_are_atomic() -> None:
    redis = AsyncMock()
    redis.eval.return_value = 1
    store = _store(redis)

    await store.record_login_failure("demo", "203.0.113.8")

    arguments = redis.eval.await_args.args
    assert arguments[1] == 1
    assert arguments[3] == "900"


@pytest.mark.asyncio
async def test_login_guard_fails_closed_when_redis_is_unavailable() -> None:
    redis = AsyncMock()
    redis.eval.side_effect = RedisError("unavailable")
    store = _store(redis)

    with pytest.raises(ServiceUnavailableError):
        await store.assert_login_allowed("demo", "203.0.113.8")


@pytest.mark.asyncio
async def test_login_limit_runs_before_user_lookup_and_password_verification() -> None:
    security_store = AsyncMock(spec=SecurityStore)
    security_store.assert_login_allowed.side_effect = RateLimitError(
        "too many login attempts; try again later",
        retry_after_seconds=60,
    )
    users = AsyncMock()
    service = AuthService(
        session=AsyncMock(),
        users=users,
        refresh_tokens=AsyncMock(),
        audit=AsyncMock(),
        security_store=security_store,
        settings=Settings(
            environment="test",
            jwt_secret_key=SecretStr("test-signing-key-with-more-than-32-characters"),
        ),
    )

    with pytest.raises(RateLimitError):
        await service.login(
            identifier="rotating-identifier",
            raw_password="Password123",  # noqa: S106
            request=RequestMetadata(ip="203.0.113.8", user_agent=None),
        )

    users.get_by_identifier.assert_not_awaited()
