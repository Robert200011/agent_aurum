"""Redis-backed security state for throttling and immediate JWT revocation."""

from __future__ import annotations

import hashlib
from collections.abc import Awaitable
from datetime import UTC, datetime
from typing import Any, Protocol, cast
from uuid import UUID

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.config import Settings
from app.errors import RateLimitError, ServiceUnavailableError

_LOGIN_GUARD_SCRIPT = """
local ip_attempts = redis.call("INCR", KEYS[1])
if ip_attempts == 1 then
    redis.call("EXPIRE", KEYS[1], ARGV[1])
end
if ip_attempts > tonumber(ARGV[2]) then
    return {1, redis.call("TTL", KEYS[1])}
end

local global_attempts = redis.call("INCR", KEYS[2])
if global_attempts == 1 then
    redis.call("EXPIRE", KEYS[2], ARGV[1])
end
if global_attempts > tonumber(ARGV[3]) then
    return {2, redis.call("TTL", KEYS[2])}
end

local failures = tonumber(redis.call("GET", KEYS[3]) or "0")
if failures >= tonumber(ARGV[4]) then
    return {3, redis.call("TTL", KEYS[3])}
end
return {0, 0}
"""

_RECORD_LOGIN_FAILURE_SCRIPT = """
local failures = redis.call("INCR", KEYS[1])
if failures == 1 then
    redis.call("EXPIRE", KEYS[1], ARGV[1])
end
return failures
"""


class SecurityStore(Protocol):
    async def assert_login_allowed(self, identifier: str, ip: str) -> None: ...

    async def record_login_failure(self, identifier: str, ip: str) -> None: ...

    async def clear_login_failures(self, identifier: str, ip: str) -> None: ...

    async def revoke_access_token(self, jti: UUID, expires_at: datetime) -> None: ...

    async def is_access_token_revoked(self, jti: UUID) -> bool: ...

    async def ping(self) -> bool: ...

    async def close(self) -> None: ...


class RedisSecurityStore:
    """Keep ephemeral security state outside application worker memory."""

    def __init__(self, redis: Redis, settings: Settings) -> None:
        self._redis = redis
        self._settings = settings

    @classmethod
    def from_settings(cls, settings: Settings) -> RedisSecurityStore:
        redis = Redis.from_url(settings.redis_url, decode_responses=True)
        return cls(redis, settings)

    @staticmethod
    def _login_key(identifier: str, ip: str) -> str:
        raw = f"{identifier.casefold()}\0{ip}".encode()
        digest = hashlib.sha256(raw).hexdigest()
        return f"aurum:security:{{login}}:failures:{digest}"

    @staticmethod
    def _login_ip_key(ip: str) -> str:
        digest = hashlib.sha256(ip.encode()).hexdigest()
        return f"aurum:security:{{login}}:requests:ip:{digest}"

    @staticmethod
    def _login_global_key() -> str:
        return "aurum:security:{login}:requests:global"

    @staticmethod
    def _revocation_key(jti: UUID) -> str:
        return f"aurum:security:revoked-access:{jti}"

    async def assert_login_allowed(self, identifier: str, ip: str) -> None:
        """原子消耗登录请求额度，并检查现有的失败锁定状态。"""

        try:
            result = await cast(
                Awaitable[Any],
                self._redis.eval(
                    _LOGIN_GUARD_SCRIPT,
                    3,
                    self._login_ip_key(ip),
                    self._login_global_key(),
                    self._login_key(identifier, ip),
                    str(self._settings.login_request_window_seconds),
                    str(self._settings.login_ip_request_limit),
                    str(self._settings.login_global_request_limit),
                    str(self._settings.login_max_failures),
                ),
            )
        except RedisError as exc:
            raise ServiceUnavailableError("security state service is unavailable") from exc

        decision = int(result[0])
        if decision != 0:
            retry_after = max(1, int(result[1]))
            raise RateLimitError(
                "too many login attempts; try again later",
                retry_after_seconds=retry_after,
            )

    async def record_login_failure(self, identifier: str, ip: str) -> None:
        key = self._login_key(identifier, ip)
        try:
            await cast(
                Awaitable[Any],
                self._redis.eval(
                    _RECORD_LOGIN_FAILURE_SCRIPT,
                    1,
                    key,
                    str(self._settings.login_failure_window_seconds),
                ),
            )
        except RedisError as exc:
            raise ServiceUnavailableError("security state service is unavailable") from exc

    async def clear_login_failures(self, identifier: str, ip: str) -> None:
        try:
            await self._redis.delete(self._login_key(identifier, ip))
        except RedisError as exc:
            raise ServiceUnavailableError("security state service is unavailable") from exc

    async def revoke_access_token(self, jti: UUID, expires_at: datetime) -> None:
        ttl = max(1, int((expires_at - datetime.now(UTC)).total_seconds()))
        try:
            await self._redis.setex(self._revocation_key(jti), ttl, "1")
        except RedisError as exc:
            raise ServiceUnavailableError("security state service is unavailable") from exc

    async def is_access_token_revoked(self, jti: UUID) -> bool:
        try:
            return bool(await self._redis.exists(self._revocation_key(jti)))
        except RedisError as exc:
            raise ServiceUnavailableError("security state service is unavailable") from exc

    async def ping(self) -> bool:
        try:
            return bool(await self._redis.ping())
        except RedisError:
            return False

    async def close(self) -> None:
        await self._redis.aclose()
