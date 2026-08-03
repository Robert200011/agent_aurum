"""只保存已发布检索标识与分数的 Redis 最小安全缓存。"""

from __future__ import annotations

import asyncio
import json
import logging
import secrets
from collections.abc import Awaitable
from dataclasses import asdict, dataclass
from time import perf_counter
from typing import Any, cast
from uuid import UUID, uuid4

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.config import Settings
from app.observability.metrics import CACHE_DURATION, CACHE_REQUESTS

logger = logging.getLogger(__name__)
_RELEASE_LOCK_SCRIPT = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
  return redis.call('DEL', KEYS[1])
end
return 0
"""


@dataclass(frozen=True, slots=True)
class CachedRetrievalItem:
    chunk_id: UUID
    document_version_id: UUID
    knowledge_base_id: UUID
    score: float
    retrieval_source: str


@dataclass(frozen=True, slots=True)
class RetrievalCacheEntry:
    items: tuple[CachedRetrievalItem, ...]
    reranker_applied: bool
    reranker_fallback_code: str | None


class RedisRetrievalCache:
    """Redis 故障时旁路；值中不含查询、正文、用户身份或最终回答。"""

    def __init__(self, redis: Redis, settings: Settings) -> None:
        self._redis = redis
        self._ttl = settings.retrieval_cache_ttl_seconds
        self._jitter = settings.retrieval_cache_ttl_jitter_seconds
        self._lock_ttl = settings.retrieval_cache_singleflight_seconds

    @classmethod
    def from_settings(cls, settings: Settings) -> RedisRetrievalCache:
        return cls(Redis.from_url(settings.redis_url, decode_responses=True), settings)

    @staticmethod
    def data_key(digest: str) -> str:
        return f"aurum:cache:retrieval:{{{digest}}}:data"

    @staticmethod
    def lock_key(digest: str) -> str:
        return f"aurum:cache:retrieval:{{{digest}}}:lock"

    async def get(self, digest: str) -> RetrievalCacheEntry | None:
        started = perf_counter()
        outcome = "bypass"
        try:
            raw = await self._redis.get(self.data_key(digest))
            if not isinstance(raw, str):
                outcome = "miss"
                return None
            decoded = json.loads(raw)
            items = tuple(
                CachedRetrievalItem(
                    chunk_id=UUID(item["chunk_id"]),
                    document_version_id=UUID(item["document_version_id"]),
                    knowledge_base_id=UUID(item["knowledge_base_id"]),
                    score=float(item["score"]),
                    retrieval_source=str(item["retrieval_source"]),
                )
                for item in decoded["items"]
            )
            outcome = "hit"
            return RetrievalCacheEntry(
                items=items,
                reranker_applied=bool(decoded["reranker_applied"]),
                reranker_fallback_code=decoded.get("reranker_fallback_code"),
            )
        except (RedisError, KeyError, TypeError, ValueError, json.JSONDecodeError):
            logger.warning("retrieval cache lookup bypassed", exc_info=True)
            return None
        finally:
            CACHE_REQUESTS.labels(cache="published_retrieval", outcome=outcome).inc()
            CACHE_DURATION.labels(cache="published_retrieval").observe(
                perf_counter() - started
            )

    async def set(self, digest: str, entry: RetrievalCacheEntry) -> None:
        payload = {
            "schema": 1,
            "items": [
                {
                    **asdict(item),
                    "chunk_id": str(item.chunk_id),
                    "document_version_id": str(item.document_version_id),
                    "knowledge_base_id": str(item.knowledge_base_id),
                }
                for item in entry.items
            ],
            "reranker_applied": entry.reranker_applied,
            "reranker_fallback_code": entry.reranker_fallback_code,
        }
        ttl = self._ttl + (secrets.randbelow(self._jitter + 1) if self._jitter else 0)
        try:
            await self._redis.set(
                self.data_key(digest),
                json.dumps(payload, separators=(",", ":")),
                ex=ttl,
            )
        except RedisError:
            logger.warning("retrieval cache write bypassed", exc_info=True)

    async def acquire_fill(self, digest: str) -> str | None:
        owner = str(uuid4())
        try:
            acquired = await self._redis.set(
                self.lock_key(digest), owner, ex=self._lock_ttl, nx=True
            )
        except RedisError:
            return None
        return owner if acquired else None

    async def wait_for_fill(self, digest: str) -> RetrievalCacheEntry | None:
        for _ in range(3):
            await asyncio.sleep(0.05)
            entry = await self.get(digest)
            if entry is not None:
                return entry
        return None

    async def release_fill(self, digest: str, owner: str) -> None:
        try:
            await cast(
                Awaitable[Any],
                self._redis.eval(
                    _RELEASE_LOCK_SCRIPT,
                    1,
                    self.lock_key(digest),
                    owner,
                ),
            )
        except RedisError:
            logger.warning("retrieval cache lock release bypassed", exc_info=True)

    async def close(self) -> None:
        await self._redis.aclose()
