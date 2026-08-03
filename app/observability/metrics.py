"""Aurum 的低基数 Prometheus 指标与观测辅助函数。"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from functools import wraps
from time import perf_counter
from typing import ParamSpec, TypeVar

from prometheus_client import REGISTRY, Counter, Gauge, Histogram, generate_latest
from starlette.types import ASGIApp, Message, Receive, Scope, Send

P = ParamSpec("P")
R = TypeVar("R")

API_REQUESTS = Counter(
    "aurum_api_requests_total",
    "Completed HTTP requests.",
    ("method", "route", "status"),
)
API_DURATION = Histogram(
    "aurum_api_request_duration_seconds",
    "End-to-end HTTP request duration, including streaming responses.",
    ("method", "route"),
)
API_IN_PROGRESS = Gauge(
    "aurum_api_requests_in_progress",
    "HTTP requests currently executing.",
    ("method",),
)
SSE_CONNECTIONS = Gauge(
    "aurum_sse_connections",
    "Open SSE response streams.",
    ("route",),
)
SSE_EVENTS = Counter(
    "aurum_sse_events_total",
    "SSE events emitted by event type.",
    ("event",),
)
MODEL_REQUESTS = Counter(
    "aurum_model_requests_total",
    "Model provider calls.",
    ("provider", "model", "mode", "outcome"),
)
MODEL_DURATION = Histogram(
    "aurum_model_request_duration_seconds",
    "Model provider call duration.",
    ("provider", "model", "mode"),
)
MODEL_TOKENS = Counter(
    "aurum_model_tokens_total",
    "Model token usage reported by the provider.",
    ("provider", "model", "kind"),
)
RETRIEVAL_REQUESTS = Counter(
    "aurum_retrieval_requests_total",
    "Knowledge retrieval calls.",
    ("mode", "outcome"),
)
RETRIEVAL_DURATION = Histogram(
    "aurum_retrieval_duration_seconds",
    "Knowledge retrieval duration.",
    ("mode",),
)
RETRIEVAL_RESULTS = Histogram(
    "aurum_retrieval_results",
    "Number of chunks returned by retrieval.",
    ("mode",),
    buckets=(0, 1, 2, 4, 6, 10, 20),
)
TOOL_REQUESTS = Counter(
    "aurum_tool_requests_total",
    "Finance tool executions.",
    ("tool", "outcome"),
)
TOOL_DURATION = Histogram(
    "aurum_tool_duration_seconds",
    "Finance tool execution duration.",
    ("tool",),
)
WORKER_TASKS = Counter(
    "aurum_worker_tasks_total",
    "Celery task executions.",
    ("task", "outcome"),
)
WORKER_DURATION = Histogram(
    "aurum_worker_task_duration_seconds",
    "Celery task execution duration.",
    ("task",),
)
WORKER_READY = Gauge(
    "aurum_worker_ready",
    "Whether the ingestion worker heartbeat is currently healthy.",
)
QUEUE_DEPTH = Gauge(
    "aurum_ingestion_queue_depth",
    "Pending messages in the ingestion queue.",
)
DB_POOL_CONNECTIONS = Gauge(
    "aurum_database_pool_connections",
    "SQLAlchemy connection pool state.",
    ("state",),
)
CACHE_REQUESTS = Counter(
    "aurum_cache_requests_total",
    "Cache lookups reserved for the P6.2 cache implementation.",
    ("cache", "outcome"),
)
CACHE_DURATION = Histogram(
    "aurum_cache_request_duration_seconds",
    "Cache lookup duration reserved for P6.2.",
    ("cache",),
)
QUOTA_REJECTIONS = Counter(
    "aurum_quota_rejections_total",
    "High-cost operations rejected by quota dimension.",
    ("resource", "scope", "reason"),
)
QUOTA_CONCURRENCY = Gauge(
    "aurum_quota_concurrency",
    "Current active high-cost leases.",
    ("resource", "scope"),
)
QUOTA_STORE_ERRORS = Counter(
    "aurum_quota_store_errors_total",
    "Quota-store operations that could not be completed.",
    ("operation",),
)


def metrics_payload() -> bytes:
    """按 Prometheus exposition format 生成当前进程指标。"""

    return generate_latest(REGISTRY)


def record_model_call(
    *,
    provider: str,
    model: str,
    mode: str,
    outcome: str,
    duration_seconds: float,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
) -> None:
    """记录模型调用元数据和用量，标签不接受请求或响应正文。"""

    MODEL_REQUESTS.labels(
        provider=provider,
        model=model,
        mode=mode,
        outcome=outcome,
    ).inc()
    MODEL_DURATION.labels(provider=provider, model=model, mode=mode).observe(
        max(0.0, duration_seconds)
    )
    if prompt_tokens:
        MODEL_TOKENS.labels(provider=provider, model=model, kind="prompt").inc(
            prompt_tokens
        )
    if completion_tokens:
        MODEL_TOKENS.labels(provider=provider, model=model, kind="completion").inc(
            completion_tokens
        )


def route_label(scope: Scope) -> str:
    """仅使用路由模板，避免把 UUID、查询或用户输入写入指标标签。"""

    route = scope.get("route")
    path = getattr(route, "path", None)
    return path if isinstance(path, str) else "unmatched"


def update_database_pool_metrics(engine: object) -> None:
    """在抓取时读取同步池计数，不把数据库 URL 放入标签。"""

    sync_engine = getattr(engine, "sync_engine", None)
    pool = getattr(sync_engine, "pool", None)
    if pool is None:
        return
    for state, accessor in (
        ("size", "size"),
        ("checked_out", "checkedout"),
        ("overflow", "overflow"),
    ):
        function = getattr(pool, accessor, None)
        if callable(function):
            DB_POOL_CONNECTIONS.labels(state=state).set(function())


class MetricsMiddleware:
    """记录包含完整 SSE 生命周期的 HTTP 数量、状态和耗时。"""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope.get("path") == "/metrics":
            await self.app(scope, receive, send)
            return
        method = str(scope.get("method", "UNKNOWN")).upper()
        status_code = 500
        is_sse = False
        started = perf_counter()
        API_IN_PROGRESS.labels(method=method).inc()

        async def observed_send(message: Message) -> None:
            nonlocal status_code, is_sse
            if message["type"] == "http.response.start":
                status_code = int(message["status"])
                headers = dict(message.get("headers", []))
                is_sse = headers.get(b"content-type", b"").startswith(b"text/event-stream")
                if is_sse:
                    SSE_CONNECTIONS.labels(route=route_label(scope)).inc()
            await send(message)

        try:
            await self.app(scope, receive, observed_send)
        finally:
            route = route_label(scope)
            elapsed = max(0.0, perf_counter() - started)
            API_IN_PROGRESS.labels(method=method).dec()
            API_REQUESTS.labels(method=method, route=route, status=str(status_code)).inc()
            API_DURATION.labels(method=method, route=route).observe(elapsed)
            if is_sse:
                SSE_CONNECTIONS.labels(route=route).dec()


def observe_retrieval(
    mode: str,
) -> Callable[[Callable[P, Awaitable[R]]], Callable[P, Awaitable[R]]]:
    """记录检索成功/失败、耗时和返回条目数，不记录查询正文。"""

    def decorate(function: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
        @wraps(function)
        async def wrapped(*args: P.args, **kwargs: P.kwargs) -> R:
            started = perf_counter()
            from app.observability.tracing import start_span

            with start_span("rag.retrieve", mode=mode):
                try:
                    result = await function(*args, **kwargs)
                except Exception:
                    RETRIEVAL_REQUESTS.labels(mode=mode, outcome="error").inc()
                    raise
                else:
                    RETRIEVAL_REQUESTS.labels(mode=mode, outcome="success").inc()
                    items = getattr(result, "items", ())
                    RETRIEVAL_RESULTS.labels(mode=mode).observe(len(items))
                    return result
                finally:
                    RETRIEVAL_DURATION.labels(mode=mode).observe(perf_counter() - started)

        return wrapped

    return decorate
