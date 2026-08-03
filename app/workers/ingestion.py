"""Celery dispatch tasks for durable knowledge-ingestion outbox events."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from app.config import get_settings
from app.db.models.rag import OutboxEvent
from app.db.session import get_session_factory
from app.providers.quota_store import RedisQuotaStore
from app.providers.s3_object_storage import S3ObjectStorageProvider
from app.providers.worker_health import record_worker_heartbeat
from app.rag.constants import (
    OUTBOX_STATUS_FAILED,
    OUTBOX_STATUS_PENDING,
    OUTBOX_STATUS_PUBLISHED,
)
from app.rag.embeddings.dashscope import DashScopeEmbeddingProvider
from app.services.ingestion import IngestionPipeline, IngestionRetryRequested
from app.workers.async_runtime import worker_async_runtime
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(  # type: ignore[untyped-decorator]
    name="app.workers.ingestion.record_ingestion_worker_heartbeat"
)
def record_ingestion_worker_heartbeat() -> str:
    """Prove that Beat scheduling, queue routing, and Worker consumption all work."""

    return record_worker_heartbeat(get_settings())


def _outbox_backoff_seconds(*, attempt_count: int, base_seconds: int, max_seconds: int) -> int:
    exponent = min(30, max(0, attempt_count - 1))
    return min(max_seconds, base_seconds * (1 << exponent))


def _apply_outbox_dispatch_failure(
    event: OutboxEvent,
    *,
    failed_at: datetime,
    error_summary: str,
    base_seconds: int,
    max_seconds: int,
) -> None:
    event.last_error = error_summary
    event.lease_owner = None
    event.lease_expires_at = None
    if event.attempt_count >= event.max_attempts:
        event.status = OUTBOX_STATUS_FAILED
        event.failed_at = failed_at
        return
    event.status = OUTBOX_STATUS_PENDING
    event.available_at = failed_at + timedelta(
        seconds=_outbox_backoff_seconds(
            attempt_count=event.attempt_count,
            base_seconds=base_seconds,
            max_seconds=max_seconds,
        )
    )


async def _dispatch_pending_outbox_events() -> int:
    from app.db.repositories.rag import RagRepository

    settings = get_settings()
    now = datetime.now(UTC)
    owner = f"outbox-dispatcher:{uuid4()}"
    async with get_session_factory()() as session:
        repository = RagRepository(session)
        exhausted = await repository.fail_exhausted_outbox_events(now=now)
        events = await repository.claim_outbox_events(
            now=now,
            lease_expires_at=now + timedelta(seconds=settings.outbox_lease_seconds),
            lease_owner=owner,
            limit=settings.outbox_dispatch_batch_size,
        )
        await session.commit()
    if exhausted:
        logger.warning(
            "exhausted outbox events moved to failed state exhausted_count=%d",
            exhausted,
        )

    dispatched = 0
    publication_failures = 0
    for event in events:
        try:
            run_ingestion_job.apply_async(args=[str(event.ingestion_job_id)], retry=False)
        except Exception as exc:
            publication_failures += 1
            logger.exception("unable to dispatch ingestion job", extra={"job_id": str(event.id)})
            failed_at = datetime.now(UTC)
            async with get_session_factory()() as session:
                repository = RagRepository(session)
                persisted = await repository.get_outbox_event_by_id(event.id, for_update=True)
                if persisted is not None and persisted.lease_owner == owner:
                    _apply_outbox_dispatch_failure(
                        persisted,
                        failed_at=failed_at,
                        error_summary=(
                            f"{type(exc).__name__}: ingestion task publication failed"
                        ),
                        base_seconds=settings.outbox_backoff_base_seconds,
                        max_seconds=settings.outbox_backoff_max_seconds,
                    )
                    await session.commit()
            continue
        async with get_session_factory()() as session:
            repository = RagRepository(session)
            persisted = await repository.get_outbox_event_by_id(event.id, for_update=True)
            if persisted is not None and persisted.lease_owner == owner:
                persisted.status = OUTBOX_STATUS_PUBLISHED
                persisted.published_at = datetime.now(UTC)
                persisted.failed_at = None
                persisted.last_error = None
                persisted.lease_owner = None
                persisted.lease_expires_at = None
                await session.commit()
                dispatched += 1

    pending_count: int | None = None
    failed_count: int | None = None
    oldest_pending_age_seconds: int | None = None
    try:
        async with get_session_factory()() as session:
            repository = RagRepository(session)
            pending_count, failed_count, oldest_pending_at = (
                await repository.get_outbox_dispatch_metrics()
            )
        if oldest_pending_at is not None:
            oldest_pending_age_seconds = max(
                0,
                int((datetime.now(UTC) - oldest_pending_at).total_seconds()),
            )
    except Exception:
        logger.exception("unable to collect outbox dispatch metrics")

    logger.info(
        "outbox dispatch scan completed claimed_count=%d dispatched_count=%d "
        "publication_failure_count=%d exhausted_count=%d pending_count=%s "
        "failed_count=%s oldest_pending_age_seconds=%s",
        len(events),
        dispatched,
        publication_failures,
        exhausted,
        pending_count,
        failed_count,
        oldest_pending_age_seconds,
    )
    return dispatched


@celery_app.task(name="app.workers.ingestion.dispatch_pending_outbox_events")  # type: ignore[untyped-decorator]
def dispatch_pending_outbox_events() -> int:
    """Deliver pending events after their database transaction is durable."""

    return worker_async_runtime.run(_dispatch_pending_outbox_events())


async def _run_ingestion_job(job_id: UUID) -> str:
    settings = get_settings()
    pipeline = IngestionPipeline(
        session_factory=get_session_factory(),
        object_storage=S3ObjectStorageProvider(settings),
        embedding_provider=DashScopeEmbeddingProvider(settings),
        settings=settings,
    )
    quota_store = RedisQuotaStore.from_settings(settings)
    try:
        result = await pipeline.run(job_id)
        await quota_store.release_upload_job(job_id)
        return result
    finally:
        await quota_store.close()


@celery_app.task(  # type: ignore[untyped-decorator]
    bind=True,
    name="app.workers.ingestion.run_ingestion_job",
)
def run_ingestion_job(self: Any, job_id: str) -> str:
    """Execute one lease-protected ingestion attempt and delay transient retries."""

    settings = get_settings()
    try:
        return worker_async_runtime.run(_run_ingestion_job(UUID(job_id)))
    except IngestionRetryRequested as exc:
        countdown = min(
            settings.outbox_backoff_max_seconds,
            settings.outbox_backoff_base_seconds * (1 << min(10, self.request.retries)),
        )
        raise self.retry(
            exc=RuntimeError(exc.code),
            countdown=countdown,
            max_retries=settings.ingestion_max_retries,
        ) from exc
