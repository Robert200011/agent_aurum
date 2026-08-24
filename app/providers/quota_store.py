"""Redis 原子配额计数、并发租约与实际用量结算。"""

from __future__ import annotations

import hashlib
from collections.abc import Awaitable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import UUID, uuid4

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.config import Settings
from app.errors import QuotaExceededError, QuotaStoreUnavailableError
from app.observability.metrics import (
    QUOTA_CONCURRENCY,
    QUOTA_REJECTIONS,
    QUOTA_STORE_ERRORS,
)

_CHAT_RESERVE_SCRIPT = """
redis.call('ZREMRANGEBYSCORE', KEYS[5], '-inf', ARGV[1])
redis.call('ZREMRANGEBYSCORE', KEYS[6], '-inf', ARGV[1])
local user_requests = tonumber(redis.call('GET', KEYS[1]) or '0')
local global_requests = tonumber(redis.call('GET', KEYS[2]) or '0')
local user_tokens = tonumber(redis.call('GET', KEYS[3]) or '0')
local global_tokens = tonumber(redis.call('GET', KEYS[4]) or '0')
if user_requests + 1 > tonumber(ARGV[3]) then return {1, redis.call('TTL', KEYS[1])} end
if global_requests + 1 > tonumber(ARGV[4]) then return {2, redis.call('TTL', KEYS[2])} end
if user_tokens + tonumber(ARGV[7]) > tonumber(ARGV[5]) then return {3, tonumber(ARGV[11])} end
if global_tokens + tonumber(ARGV[7]) > tonumber(ARGV[6]) then return {4, tonumber(ARGV[11])} end
if redis.call('ZCARD', KEYS[5]) >= tonumber(ARGV[8]) then return {5, tonumber(ARGV[9])} end
if redis.call('ZCARD', KEYS[6]) >= tonumber(ARGV[9 + 1]) then return {6, tonumber(ARGV[9])} end
local next_user_requests = redis.call('INCR', KEYS[1])
if next_user_requests == 1 then redis.call('EXPIRE', KEYS[1], ARGV[2]) end
local next_global_requests = redis.call('INCR', KEYS[2])
if next_global_requests == 1 then redis.call('EXPIRE', KEYS[2], ARGV[2]) end
redis.call('INCRBY', KEYS[3], ARGV[7]); redis.call('EXPIRE', KEYS[3], ARGV[11])
redis.call('INCRBY', KEYS[4], ARGV[7]); redis.call('EXPIRE', KEYS[4], ARGV[11])
local expires = tonumber(ARGV[1]) + tonumber(ARGV[9])
redis.call('ZADD', KEYS[5], expires, ARGV[12])
redis.call('ZADD', KEYS[6], expires, ARGV[12])
redis.call('HSET', KEYS[7], 'reserved', ARGV[7])
redis.call('EXPIRE', KEYS[7], ARGV[9])
return {0, redis.call('ZCARD', KEYS[5]), redis.call('ZCARD', KEYS[6])}
"""

# ARGV indexes are deliberately explicit in this shorter script because quota
# checks and all mutations must remain one indivisible Redis operation.
_CHAT_SETTLE_SCRIPT = """
local reserved = redis.call('HGET', KEYS[5], 'reserved')
if not reserved then return {0} end
local delta = tonumber(ARGV[1]) - tonumber(reserved)
if delta ~= 0 then
  redis.call('INCRBY', KEYS[1], delta)
  redis.call('INCRBY', KEYS[2], delta)
end
redis.call('ZREM', KEYS[3], ARGV[2])
redis.call('ZREM', KEYS[4], ARGV[2])
redis.call('DEL', KEYS[5])
return {1, redis.call('ZCARD', KEYS[4])}
"""

_MODEL_CALL_RESERVE_SCRIPT = """
local current = tonumber(redis.call('GET', KEYS[1]) or '0')
if current + 1 > tonumber(ARGV[2]) then return {1, redis.call('TTL', KEYS[1])} end
local next_calls = redis.call('INCR', KEYS[1])
if next_calls == 1 then redis.call('EXPIRE', KEYS[1], ARGV[1]) end
return {0, next_calls}
"""


def _subject_hash(user_id: UUID) -> str:
    return hashlib.sha256(user_id.bytes).hexdigest()


def _periods() -> tuple[int, int, str]:
    now = datetime.now(UTC)
    seconds_to_minute = max(1, 60 - now.second)
    tomorrow = datetime.combine(now.date() + timedelta(days=1), datetime.min.time(), UTC)
    seconds_to_day = max(1, int((tomorrow - now).total_seconds()))
    return seconds_to_minute, seconds_to_day, now.date().isoformat()


@dataclass(frozen=True, slots=True)
class ChatQuotaLease:
    store: RedisQuotaStore
    reservation_id: str
    user_hash: str
    day: str

    async def settle(self, actual_tokens: int) -> None:
        await self.store.settle_chat(self, actual_tokens=max(0, actual_tokens))


class RedisQuotaStore:
    """对模型入口 fail-closed，对结算失败采用租约 TTL 兜底。"""

    def __init__(self, redis: Redis, settings: Settings) -> None:
        self._redis = redis
        self._settings = settings

    @classmethod
    def from_settings(cls, settings: Settings) -> RedisQuotaStore:
        return cls(Redis.from_url(settings.redis_url, decode_responses=True), settings)

    @staticmethod
    def _key(suffix: str) -> str:
        return f"aurum:quota:{{quota}}:{suffix}"

    async def reserve_chat(self, user_id: UUID) -> ChatQuotaLease:
        subject = _subject_hash(user_id)
        minute_ttl, day_ttl, day = _periods()
        reservation_id = str(uuid4())
        keys = (
            self._key(f"chat:req:user:{subject}"),
            self._key("chat:req:global"),
            self._key(f"chat:tokens:user:{subject}:{day}"),
            self._key(f"chat:tokens:global:{day}"),
            self._key(f"chat:leases:user:{subject}"),
            self._key("chat:leases:global"),
            self._key(f"chat:reservation:{reservation_id}"),
        )
        try:
            result = await cast(
                Awaitable[Any],
                self._redis.eval(
                    _CHAT_RESERVE_SCRIPT,
                    len(keys),
                    *keys,
                    str(int(datetime.now(UTC).timestamp())),
                    str(minute_ttl),
                    str(self._settings.quota_chat_user_requests_per_minute),
                    str(self._settings.quota_chat_global_requests_per_minute),
                    str(self._settings.quota_user_daily_model_tokens),
                    str(self._settings.quota_global_daily_model_tokens),
                    str(self._settings.quota_model_tokens_reserved_per_request),
                    str(self._settings.quota_user_agent_concurrency),
                    str(self._settings.quota_agent_lease_seconds),
                    str(self._settings.quota_global_agent_concurrency),
                    str(day_ttl),
                    reservation_id,
                ),
            )
        except RedisError as exc:
            QUOTA_STORE_ERRORS.labels(operation="reserve_chat").inc()
            raise QuotaStoreUnavailableError("quota state service is unavailable") from exc
        self._raise_chat_rejection(result)
        QUOTA_CONCURRENCY.labels(resource="agent", scope="global").set(int(result[2]))
        return ChatQuotaLease(self, reservation_id, subject, day)

    async def reserve_model_call(self) -> None:
        """在每次真实 Chat Provider 请求前占用全局分钟额度。"""

        minute_ttl, _, _ = _periods()
        try:
            result = await cast(
                Awaitable[Any],
                self._redis.eval(
                    _MODEL_CALL_RESERVE_SCRIPT,
                    1,
                    self._key("model:req:global"),
                    str(minute_ttl),
                    str(self._settings.quota_global_model_requests_per_minute),
                ),
            )
        except RedisError as exc:
            QUOTA_STORE_ERRORS.labels(operation="reserve_model_call").inc()
            raise QuotaStoreUnavailableError("quota state service is unavailable") from exc
        if int(result[0]) == 0:
            return
        QUOTA_REJECTIONS.labels(
            resource="model", scope="global", reason="requests"
        ).inc()
        raise QuotaExceededError(
            "global model request quota exceeded; try again later",
            code="quota_global_model_requests_exceeded",
            retry_after_seconds=max(1, int(result[1])),
        )

    def _raise_chat_rejection(self, result: Any) -> None:
        decision = int(result[0])
        if decision == 0:
            return
        choices = {
            1: ("user", "requests", "quota_user_chat_requests_exceeded"),
            2: ("global", "requests", "quota_global_chat_requests_exceeded"),
            3: ("user", "tokens", "quota_user_model_tokens_exceeded"),
            4: ("global", "tokens", "quota_global_model_tokens_exceeded"),
            5: ("user", "concurrency", "quota_user_agent_concurrency_exceeded"),
            6: ("global", "concurrency", "quota_global_agent_concurrency_exceeded"),
        }
        scope, reason, code = choices[decision]
        QUOTA_REJECTIONS.labels(resource="chat", scope=scope, reason=reason).inc()
        raise QuotaExceededError(
            "chat quota exceeded; try again later",
            code=code,
            retry_after_seconds=max(1, int(result[1])),
        )

    async def settle_chat(self, lease: ChatQuotaLease, *, actual_tokens: int) -> None:
        keys = (
            self._key(f"chat:tokens:user:{lease.user_hash}:{lease.day}"),
            self._key(f"chat:tokens:global:{lease.day}"),
            self._key(f"chat:leases:user:{lease.user_hash}"),
            self._key("chat:leases:global"),
            self._key(f"chat:reservation:{lease.reservation_id}"),
        )
        try:
            result = await cast(
                Awaitable[Any],
                self._redis.eval(
                    _CHAT_SETTLE_SCRIPT,
                    len(keys),
                    *keys,
                    str(actual_tokens),
                    lease.reservation_id,
                ),
            )
        except RedisError:
            QUOTA_STORE_ERRORS.labels(operation="settle_chat").inc()
            return
        if int(result[0]) == 1:
            QUOTA_CONCURRENCY.labels(resource="agent", scope="global").set(int(result[1]))

    async def close(self) -> None:
        await self._redis.aclose()

    async def current_global_concurrency(self) -> int:
        """按租约到期分数读取当前全局 Agent 处理数。"""

        now = int(datetime.now(UTC).timestamp())
        try:
            result = await self._redis.zcount(
                self._key("chat:leases:global"), now + 1, "+inf"
            )
        except RedisError as exc:
            QUOTA_STORE_ERRORS.labels(operation="read_concurrency").inc()
            raise QuotaStoreUnavailableError("quota state service is unavailable") from exc
        return int(result)
