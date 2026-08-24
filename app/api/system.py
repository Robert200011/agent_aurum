"""Liveness and dependency readiness probes."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Response, status
from sqlalchemy import text

from app.api.dependencies import (
    SecurityStoreDependency,
    SessionDependency,
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
    ready_now = database_ok and redis_ok
    if not ready_now:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {
        "status": "ready" if ready_now else "not_ready",
        "dependencies": {
            "database": database_ok,
            "redis": redis_ok,
        },
    }
