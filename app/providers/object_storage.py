"""Object-storage provider contract for knowledge-document lifecycle operations."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import timedelta
from typing import Protocol


@dataclass(frozen=True, slots=True)
class ObjectMetadata:
    """Verified object metadata returned by the storage boundary."""

    object_key: str
    content_length: int
    content_type: str | None
    etag: str | None
    checksum_sha256: str | None
    metadata: Mapping[str, str]


class ObjectStorageProvider(Protocol):
    async def check_readiness(self) -> None: ...

    async def put(
        self,
        object_key: str,
        content: bytes,
        content_type: str,
        *,
        metadata: Mapping[str, str] | None = None,
        checksum_sha256: str | None = None,
    ) -> ObjectMetadata: ...

    async def get(self, object_key: str) -> bytes: ...

    async def head(self, object_key: str) -> ObjectMetadata: ...

    async def delete(self, object_key: str) -> None: ...

    async def create_presigned_download_url(
        self,
        object_key: str,
        *,
        expires_in: timedelta,
    ) -> str: ...
