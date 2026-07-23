"""Object-storage provider contract for uploaded knowledge documents."""

from __future__ import annotations

from typing import Protocol


class ObjectStorageProvider(Protocol):
    async def put(self, object_key: str, content: bytes, content_type: str) -> None: ...

    async def get(self, object_key: str) -> bytes: ...
