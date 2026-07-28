"""Redis-backed proof that Beat can schedule work and a Worker can consume it."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol

from redis import Redis as SyncRedis
from redis.asyncio import Redis as AsyncRedis
from redis.exceptions import RedisError

from app.config import Settings

WORKER_HEARTBEAT_KEY = "aurum:health:ingestion-worker-heartbeat"


class WorkerHealthStore(Protocol):
    async def is_ready(self) -> bool: ...

    async def close(self) -> None: ...


class RedisWorkerHealthStore:
    """Read the expiring heartbeat written only by an executing Worker task."""

    def __init__(self, redis: AsyncRedis) -> None:
        self._redis = redis

    @classmethod
    def from_settings(cls, settings: Settings) -> RedisWorkerHealthStore:
        return cls(AsyncRedis.from_url(settings.redis_url, decode_responses=True))

    async def is_ready(self) -> bool:
        try:
            value, ttl = await self._redis.get(WORKER_HEARTBEAT_KEY), await self._redis.ttl(
                WORKER_HEARTBEAT_KEY
            )
            return bool(value) and int(ttl) > 0
        except RedisError:
            return False

    async def close(self) -> None:
        await self._redis.aclose()


def record_worker_heartbeat(settings: Settings) -> str:
    """Write one short-lived marker from the synchronous Celery task process."""

    recorded_at = datetime.now(UTC).isoformat()
    redis = SyncRedis.from_url(settings.redis_url, decode_responses=True)
    try:
        redis.set(WORKER_HEARTBEAT_KEY, recorded_at, ex=settings.worker_heartbeat_ttl_seconds)
    finally:
        redis.close()
    return recorded_at
