"""Redis-backed security state for throttling and immediate JWT revocation."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.config import Settings
from app.errors import RateLimitError, ServiceUnavailableError


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
        return f"aurum:security:login-failures:{digest}"

    @staticmethod
    def _revocation_key(jti: UUID) -> str:
        return f"aurum:security:revoked-access:{jti}"

    async def assert_login_allowed(self, identifier: str, ip: str) -> None:
        try:
            attempts = await self._redis.get(self._login_key(identifier, ip))
        except RedisError as exc:
            raise ServiceUnavailableError("security state service is unavailable") from exc
        if attempts is not None and int(attempts) >= self._settings.login_max_failures:
            raise RateLimitError("too many failed login attempts; try again later")

    async def record_login_failure(self, identifier: str, ip: str) -> None:
        key = self._login_key(identifier, ip)
        try:
            attempts = await self._redis.incr(key)
            if attempts == 1:
                await self._redis.expire(key, self._settings.login_failure_window_seconds)
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
