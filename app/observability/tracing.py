"""可关闭、失败隔离且不采集业务正文的 OpenTelemetry 底座。"""

from __future__ import annotations

import logging
from collections.abc import Callable
from contextlib import AbstractContextManager
from threading import Lock
from typing import TYPE_CHECKING, Any

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.celery import CeleryInstrumentor
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

if TYPE_CHECKING:
    from celery import Celery  # type: ignore[import-untyped]
    from fastapi import FastAPI
    from sqlalchemy.ext.asyncio import AsyncEngine

    from app.config import Settings

logger = logging.getLogger(__name__)
_LOCK = Lock()
_PROVIDER: TracerProvider | None = None
_FASTAPI_APPS: set[int] = set()


def configure_tracing(settings: Settings) -> TracerProvider | None:
    """惰性创建 OTLP Trace Provider；关闭时完全不建立导出线程。"""

    global _PROVIDER
    if not settings.otel_tracing_enabled:
        return None
    with _LOCK:
        if _PROVIDER is not None:
            return _PROVIDER
        try:
            provider = TracerProvider(
                resource=Resource.create(
                    {
                        "service.name": settings.otel_service_name,
                        "deployment.environment.name": settings.environment,
                    }
                )
            )
            exporter = OTLPSpanExporter(
                endpoint=settings.otel_exporter_otlp_traces_endpoint,
                timeout=settings.otel_export_timeout_seconds,
            )
            provider.add_span_processor(BatchSpanProcessor(exporter))
            trace.set_tracer_provider(provider)
            _PROVIDER = provider
        except Exception:
            logger.exception("unable to initialize trace exporter")
            return None
    return _PROVIDER


def instrument_fastapi(app: FastAPI, settings: Settings) -> None:
    """添加 FastAPI 服务端 Span；排除探针和指标抓取噪声。"""

    provider = configure_tracing(settings)
    if provider is None or id(app) in _FASTAPI_APPS:
        return
    try:
        FastAPIInstrumentor.instrument_app(
            app,
            tracer_provider=provider,
            excluded_urls="/metrics,/api/v1/health/live",
        )
        _FASTAPI_APPS.add(id(app))
    except Exception:
        logger.exception("unable to instrument FastAPI tracing")


def instrument_runtime(
    settings: Settings,
    *,
    engine: AsyncEngine | None = None,
    celery_app: Celery | None = None,
) -> None:
    """接入数据库、Redis 和 Celery；任何观测初始化失败均只降级观测能力。"""

    provider = configure_tracing(settings)
    if provider is None:
        return
    operations: tuple[tuple[str, Callable[[], object]], ...] = (
        (
            "redis",
            lambda: RedisInstrumentor().instrument(tracer_provider=provider),
        ),
        (
            "sqlalchemy",
            lambda: (
                SQLAlchemyInstrumentor().instrument(
                    engine=engine.sync_engine,
                    tracer_provider=provider,
                )
                if engine is not None
                else None
            ),
        ),
        (
            "celery",
            lambda: (
                CeleryInstrumentor().instrument(  # type: ignore[no-untyped-call]
                    tracer_provider=provider,
                )
                if celery_app is not None
                else None
            ),
        ),
    )
    for name, operation in operations:
        try:
            operation()
        except Exception:
            logger.exception("unable to instrument runtime component", extra={"operation": name})


def start_span(name: str, **attributes: str | int | float | bool) -> AbstractContextManager[Any]:
    """创建仅含受控属性的业务 Span；未启用 SDK 时自动成为 No-op。"""

    tracer = trace.get_tracer("aurum-agent")
    return tracer.start_as_current_span(name, attributes=attributes)


def current_trace_id() -> str | None:
    """返回当前有效 Trace ID 的十六进制表示。"""

    span_context = trace.get_current_span().get_span_context()
    if not span_context.is_valid:
        return None
    return f"{span_context.trace_id:032x}"
