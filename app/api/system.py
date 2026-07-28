"""Liveness and dependency readiness probes."""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Response, status
from sqlalchemy import text

from app.api.dependencies import (
    ObjectStorageDependency,
    SecurityStoreDependency,
    SessionDependency,
    SettingsDependency,
    WorkerHealthStoreDependency,
)

router = APIRouter(prefix="/health", tags=["system"])
logger = logging.getLogger(__name__)


@router.get("/live")
async def live() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready")
async def ready(
    response: Response,
    session: SessionDependency,
    security_store: SecurityStoreDependency,
    object_storage: ObjectStorageDependency,
    worker_health_store: WorkerHealthStoreDependency,
    settings: SettingsDependency,
) -> dict[str, object]:
    database_ok = False
    try:
        database_ok = (await session.scalar(text("SELECT 1"))) == 1
    except Exception:
        logger.warning("database readiness check failed", exc_info=True)
        database_ok = False
    try:
        redis_ok = await security_store.ping()
    except Exception:
        logger.warning("redis readiness check failed", exc_info=True)
        redis_ok = False
    try:
        ingestion_worker_ok = await worker_health_store.is_ready()
    except Exception:
        logger.warning("ingestion-worker readiness check failed", exc_info=True)
        ingestion_worker_ok = False
    try:
        async with asyncio.timeout(settings.object_storage_readiness_timeout_seconds):
            await object_storage.check_readiness()
        object_storage_ok = True
    except Exception:
        logger.warning("object-storage readiness check failed", exc_info=True)
        object_storage_ok = False
    ready_now = database_ok and redis_ok and object_storage_ok and ingestion_worker_ok
    if not ready_now:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {
        "status": "ready" if ready_now else "not_ready",
        "dependencies": {
            "database": database_ok,
            "redis": redis_ok,
            "object_storage": object_storage_ok,
            "ingestion_worker": ingestion_worker_ok,
        },
    }
