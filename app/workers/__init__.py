"""Asynchronous ingestion and scheduled task workers."""

from app.workers.celery_app import celery_app

__all__ = ["celery_app"]
