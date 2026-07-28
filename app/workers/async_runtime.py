"""Process-local asyncio lifecycle for synchronous Celery task entrypoints."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine
from os import getpid
from threading import RLock
from typing import Any, TypeVar

from app.db.session import dispose_database_runtime, reset_database_runtime

ResultT = TypeVar("ResultT")


class WorkerAsyncRuntime:
    """Keep one event loop and its async database pool together per worker process."""

    def __init__(
        self,
        *,
        reset_database: Callable[[], None] = reset_database_runtime,
        dispose_database: Callable[[], Coroutine[Any, Any, None]] = dispose_database_runtime,
    ) -> None:
        self._reset_database = reset_database
        self._dispose_database = dispose_database
        self._lock = RLock()
        self._pid: int | None = None
        self._runner: asyncio.Runner | None = None

    def initialize(self) -> None:
        """Create a fresh runtime after Celery forks a worker child."""

        with self._lock:
            process_id = getpid()
            if self._pid == process_id and self._runner is not None:
                return

            # A forked child must never reuse the parent's loop or pooled connections.
            self._runner = None
            self._reset_database()
            self._pid = process_id
            self._runner = asyncio.Runner()

    def run(self, coroutine: Coroutine[Any, Any, ResultT]) -> ResultT:
        """Run a coroutine on the stable event loop owned by the current process."""

        with self._lock:
            self.initialize()
            if self._runner is None:  # pragma: no cover - guarded by initialize
                raise RuntimeError("worker async runtime failed to initialize")
            return self._runner.run(coroutine)

    def close(self) -> None:
        """Dispose async resources on their owning loop before process shutdown."""

        with self._lock:
            runner = self._runner
            if runner is None or self._pid != getpid():
                self._runner = None
                self._pid = None
                self._reset_database()
                return

            try:
                runner.run(self._dispose_database())
            finally:
                runner.close()
                self._runner = None
                self._pid = None


worker_async_runtime = WorkerAsyncRuntime()
