"""FastAPI application factory and process lifecycle."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import uuid4

import uvicorn
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.api.router import router as v1_router
from app.config import Settings, get_settings
from app.db.session import get_engine, get_session_factory
from app.errors import ApplicationError, RateLimitError
from app.observability.logging import configure_logging
from app.providers.identity import RedisSecurityStore
from app.providers.s3_object_storage import S3ObjectStorageProvider
from app.providers.worker_health import RedisWorkerHealthStore
from app.services.admin import bootstrap_admin

logger = logging.getLogger(__name__)


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Attach a correlation ID and conservative browser security headers."""

    async def dispatch(self, request: Request, call_next):  # type: ignore[no-untyped-def]
        request_id = request.headers.get("x-request-id") or str(uuid4())
        request.state.request_id = request_id[:128]
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        return response


def _error_payload(request: Request, *, code: str, message: str) -> dict[str, object]:
    return {
        "error": {
            "code": code,
            "message": message,
            "request_id": getattr(request.state, "request_id", None),
        }
    }


def create_app(settings: Settings | None = None) -> FastAPI:
    app_settings = settings or get_settings()
    configure_logging(app_settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        security_store = RedisSecurityStore.from_settings(app_settings)
        worker_health_store = RedisWorkerHealthStore.from_settings(app_settings)
        app.state.security_store = security_store
        app.state.worker_health_store = worker_health_store
        app.state.object_storage = S3ObjectStorageProvider(app_settings)
        if app_settings.bootstrap_admin:
            await bootstrap_admin(get_session_factory(), app_settings)
        try:
            yield
        finally:
            await worker_health_store.close()
            await security_store.close()
            await get_engine().dispose()

    app = FastAPI(
        title=app_settings.app_name,
        version="0.1.0",
        debug=app_settings.debug,
        lifespan=lifespan,
        docs_url="/docs" if not app_settings.is_production else None,
        redoc_url="/redoc" if not app_settings.is_production else None,
    )
    app.state.settings = app_settings
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=app_settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "Idempotency-Key", "X-Request-ID"],
    )

    @app.exception_handler(ApplicationError)
    async def application_error_handler(request: Request, exc: ApplicationError) -> JSONResponse:
        headers: dict[str, str] | None = None
        if exc.status_code == 401:
            headers = {"WWW-Authenticate": "Bearer"}
        elif isinstance(exc, RateLimitError):
            headers = {"Retry-After": str(exc.retry_after_seconds)}
        return JSONResponse(
            status_code=exc.status_code,
            content=_error_payload(request, code=exc.code, message=exc.message),
            headers=headers,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                **_error_payload(
                    request,
                    code="validation_error",
                    message="request validation failed",
                ),
                "details": exc.errors(),
            },
        )

    @app.exception_handler(Exception)
    async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled request error")
        return JSONResponse(
            status_code=500,
            content=_error_payload(
                request,
                code="internal_error",
                message="an internal error occurred",
            ),
        )

    app.include_router(v1_router, prefix=app_settings.api_v1_prefix)
    return app


app = create_app()


def run_server() -> None:
    """Start a local server when this file is executed directly."""

    settings = get_settings()
    uvicorn.run(
        app,
        host=settings.server_host,
        port=settings.direct_server_port,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    run_server()
