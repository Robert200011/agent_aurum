"""Celery application dedicated to asynchronous knowledge ingestion."""

from __future__ import annotations

from contextvars import ContextVar, Token
from time import perf_counter

from celery import Celery  # type: ignore[import-untyped]
from celery.signals import (  # type: ignore[import-untyped]
    task_postrun,
    task_prerun,
    worker_process_init,
    worker_process_shutdown,
    worker_shutdown,
)

from app.config import Settings, get_settings
from app.observability.context import reset_context, set_context
from app.observability.logging import configure_logging
from app.observability.metrics import WORKER_DURATION, WORKER_TASKS
from app.observability.tracing import instrument_runtime
from app.workers.async_runtime import worker_async_runtime

_TASK_STARTED: ContextVar[float | None] = ContextVar("aurum_task_started", default=None)
_TASK_CONTEXT: ContextVar[tuple[tuple[str, Token[str | None]], ...] | None] = ContextVar(
    "aurum_task_context",
    default=None,
)


@task_prerun.connect(weak=False)  # type: ignore[untyped-decorator]
def observe_task_start(task_id: str | None = None, **_: object) -> None:
    """为 Worker 任务建立可安全传播的关联上下文。"""

    _TASK_STARTED.set(perf_counter())
    tokens = set_context(request_id=task_id)
    _TASK_CONTEXT.set(tokens)


@task_postrun.connect(weak=False)  # type: ignore[untyped-decorator]
def observe_task_end(
    task: object = None,
    state: str | None = None,
    **_: object,
) -> None:
    """按固定任务名和有限终态记录 Worker 指标。"""

    name = str(getattr(task, "name", "unknown"))
    outcome = "success" if state == "SUCCESS" else "error"
    WORKER_TASKS.labels(task=name, outcome=outcome).inc()
    started = _TASK_STARTED.get()
    if started is not None:
        WORKER_DURATION.labels(task=name).observe(perf_counter() - started)
    tokens = _TASK_CONTEXT.get()
    if tokens is not None:
        reset_context(tokens)
    _TASK_STARTED.set(None)
    _TASK_CONTEXT.set(None)


@worker_process_init.connect(weak=False)  # type: ignore[untyped-decorator]
def initialize_worker_async_runtime(**_: object) -> None:
    """Detach forked workers from any parent loop and database pool."""

    worker_async_runtime.initialize()


@worker_process_shutdown.connect(weak=False)  # type: ignore[untyped-decorator]
def shutdown_worker_process_async_runtime(**_: object) -> None:
    """Release each prefork child's async resources on its owning loop."""

    worker_async_runtime.close()


@worker_shutdown.connect(weak=False)  # type: ignore[untyped-decorator]
def shutdown_worker_async_runtime(**_: object) -> None:
    """Also cover non-prefork worker pools that execute tasks in the main process."""

    worker_async_runtime.close()


def create_celery_app(settings: Settings) -> Celery:
    """由同一 Settings 实例生成生产、路由、Beat 和消费侧共享的队列配置。"""

    application = Celery(
        "aurum_ingestion",
        broker=settings.redis_url,
        include=["app.workers.ingestion"],
    )
    application.conf.update(
        task_default_queue=settings.ingestion_queue_name,
        task_routes={
            "app.workers.ingestion.dispatch_pending_outbox_events": {
                "queue": settings.ingestion_queue_name
            },
            "app.workers.ingestion.run_ingestion_job": {
                "queue": settings.ingestion_queue_name
            },
            "app.workers.ingestion.record_ingestion_worker_heartbeat": {
                "queue": settings.ingestion_queue_name
            },
        },
        beat_schedule={
            "dispatch-pending-ingestion-outbox-events": {
                "task": "app.workers.ingestion.dispatch_pending_outbox_events",
                "schedule": settings.outbox_dispatch_interval_seconds,
                "options": {"queue": settings.ingestion_queue_name},
            },
            "record-ingestion-worker-heartbeat": {
                "task": "app.workers.ingestion.record_ingestion_worker_heartbeat",
                "schedule": settings.worker_heartbeat_interval_seconds,
                "options": {"queue": settings.ingestion_queue_name},
            }
        },
        task_serializer="json",
        result_serializer="json",
        accept_content=["json"],
        task_track_started=True,
        task_time_limit=settings.ingestion_task_timeout_seconds,
        task_soft_time_limit=max(1, settings.ingestion_task_timeout_seconds - 30),
        task_acks_late=True,
        task_reject_on_worker_lost=True,
        worker_prefetch_multiplier=1,
        broker_connection_retry_on_startup=True,
        worker_hijack_root_logger=False,
        worker_redirect_stdouts=False,
    )
    configure_logging(settings.log_level, settings.otel_service_name)
    instrument_runtime(settings, celery_app=application)
    return application


celery_app = create_celery_app(get_settings())
