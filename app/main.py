"""FastAPI application factory and process lifecycle."""

from __future__ import annotations

import asyncio
import logging
import re
import sys
from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager
from time import perf_counter
from uuid import uuid4

import uvicorn
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from redis.asyncio import Redis
from starlette.middleware.base import BaseHTTPMiddleware

from app.agents.checkpoints import (
    checkpoint_connection_url,
    encrypted_checkpoint_serializer,
)
from app.api.router import router as v1_router
from app.chat.providers.dashscope import DashScopeChatModelProvider
from app.config import Settings, get_settings
from app.db.session import get_engine, get_session_factory
from app.errors import ApplicationError, RateLimitError
from app.observability.context import reset_context, set_context
from app.observability.logging import configure_logging
from app.observability.metrics import (
    QUEUE_DEPTH,
    QUOTA_CONCURRENCY,
    WORKER_READY,
    MetricsMiddleware,
    metrics_payload,
    update_database_pool_metrics,
)
from app.observability.tracing import (
    current_trace_id,
    instrument_fastapi,
    instrument_runtime,
)
from app.providers.identity import RedisSecurityStore
from app.providers.quota_store import RedisQuotaStore
from app.providers.retrieval_cache import RedisRetrievalCache
from app.providers.s3_object_storage import S3ObjectStorageProvider
from app.providers.worker_health import RedisWorkerHealthStore
from app.rag.rerankers.dashscope import DashScopeRerankerProvider
from app.services.admin import bootstrap_admin
from app.services.chat_runs import ChatRunCoordinator

logger = logging.getLogger(__name__)
_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


class RequestContextMiddleware(BaseHTTPMiddleware):
    """传播关联 ID、输出请求摘要并添加保守的浏览器安全响应头。"""

    async def dispatch(self, request: Request, call_next):  # type: ignore[no-untyped-def]
        supplied_request_id = request.headers.get("x-request-id", "")
        request_id = (
            supplied_request_id
            if _REQUEST_ID_PATTERN.fullmatch(supplied_request_id)
            else str(uuid4())
        )
        request.state.request_id = request_id
        trace_id = current_trace_id()
        request.state.trace_id = trace_id
        tokens = set_context(
            request_id=request.state.request_id,
            trace_id=trace_id,
            conversation_id=None,
            agent_run_id=None,
            user_hash=None,
        )
        started = perf_counter()
        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = request.state.request_id
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["X-Frame-Options"] = "DENY"
            response.headers["Referrer-Policy"] = "no-referrer"
            response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
            logger.info(
                "http request completed",
                extra={
                    "event": "http_request_completed",
                    "method": request.method,
                    "route": getattr(request.scope.get("route"), "path", "unmatched"),
                    "status_code": response.status_code,
                    "duration_ms": round((perf_counter() - started) * 1000),
                    "outcome": "success" if response.status_code < 500 else "error",
                },
            )
            return response
        finally:
            reset_context(tokens)


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
    configure_logging(app_settings.log_level, app_settings.otel_service_name)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        security_store = RedisSecurityStore.from_settings(app_settings)
        worker_health_store = RedisWorkerHealthStore.from_settings(app_settings)
        app.state.security_store = security_store
        app.state.worker_health_store = worker_health_store
        app.state.quota_store = RedisQuotaStore.from_settings(app_settings)
        app.state.retrieval_cache = RedisRetrievalCache.from_settings(app_settings)
        app.state.metrics_redis = Redis.from_url(app_settings.redis_url)
        app.state.object_storage = S3ObjectStorageProvider(app_settings)
        app.state.chat_model = DashScopeChatModelProvider(
            app_settings,
            quota_store=app.state.quota_store,
        )
        app.state.reranker = (
            DashScopeRerankerProvider(app_settings)
            if app_settings.rag_reranker_enabled
            else None
        )
        instrument_runtime(app_settings, engine=get_engine())
        if app_settings.bootstrap_admin:
            await bootstrap_admin(get_session_factory(), app_settings)
        serializer = encrypted_checkpoint_serializer(
            app_settings.langgraph_aes_key_bytes
        )
        owner_url = checkpoint_connection_url(app_settings.migration_database_url)
        runtime_url = checkpoint_connection_url(app_settings.database_url)
        try:
            async with AsyncPostgresSaver.from_conn_string(
                owner_url,
                serde=serializer,
            ) as setup_saver:
                await setup_saver.setup()
            async with AsyncExitStack() as stack:
                app.state.checkpointer = await stack.enter_async_context(
                    AsyncPostgresSaver.from_conn_string(
                        runtime_url,
                        serde=serializer,
                    )
                )
                app.state.chat_run_coordinator = ChatRunCoordinator(
                    settings=app_settings,
                    session_factory=get_session_factory(),
                    chat_provider=app.state.chat_model,
                    reranker_provider=app.state.reranker,
                    checkpointer=app.state.checkpointer,
                    quota_store=app.state.quota_store,
                    retrieval_cache=app.state.retrieval_cache,
                )
                try:
                    yield
                finally:
                    await app.state.chat_run_coordinator.close()
        finally:
            await app.state.chat_model.close()
            if app.state.reranker is not None:
                await app.state.reranker.close()
            await worker_health_store.close()
            await security_store.close()
            await app.state.quota_store.close()
            await app.state.retrieval_cache.close()
            await app.state.metrics_redis.aclose()
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
    if app_settings.metrics_enabled:
        app.add_middleware(MetricsMiddleware)
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

    if app_settings.metrics_enabled:

        @app.get("/metrics", include_in_schema=False)
        async def prometheus_metrics() -> Response:
            update_database_pool_metrics(get_engine())
            try:
                WORKER_READY.set(await app.state.worker_health_store.is_ready())
                QUEUE_DEPTH.set(
                    await app.state.metrics_redis.llen(app_settings.ingestion_queue_name)
                )
                agent_concurrency, upload_concurrency = (
                    await app.state.quota_store.current_global_concurrency()
                )
                QUOTA_CONCURRENCY.labels(resource="agent", scope="global").set(
                    agent_concurrency
                )
                QUOTA_CONCURRENCY.labels(resource="upload", scope="global").set(
                    upload_concurrency
                )
            except Exception:
                logger.warning("runtime metric collection failed", exc_info=True)
            return Response(
                content=metrics_payload(),
                media_type="text/plain; version=0.0.4; charset=utf-8",
            )

    app.include_router(v1_router, prefix=app_settings.api_v1_prefix)
    instrument_fastapi(app, app_settings)
    return app


app = create_app()


def windows_selector_loop_factory() -> asyncio.AbstractEventLoop:
    """Create the event loop required by async psycopg on Windows."""

    return asyncio.SelectorEventLoop()


def run_server() -> None:
    """Start a local server when this file is executed directly."""

    settings = get_settings()
    uvicorn.run(
        app,
        host=settings.server_host,
        port=settings.direct_server_port,
        log_level=settings.log_level.lower(),
        log_config=None,
        access_log=False,
        loop=(
            "app.main:windows_selector_loop_factory"
            if sys.platform == "win32"
            else "auto"
        ),
    )


if __name__ == "__main__":
    run_server()
