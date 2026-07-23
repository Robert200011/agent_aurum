"""Liveness and dependency readiness probes."""

from __future__ import annotations

from fastapi import APIRouter, Response, status
from sqlalchemy import text

from app.api.dependencies import SecurityStoreDependency, SessionDependency

router = APIRouter(prefix="/health", tags=["system"])


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
        database_ok = False
    redis_ok = await security_store.ping()
    ready_now = database_ok and redis_ok
    if not ready_now:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {
        "status": "ready" if ready_now else "not_ready",
        "dependencies": {"database": database_ok, "redis": redis_ok},
    }
