"""Vector-store provider contract independent from SQLAlchemy and pgvector."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID


@dataclass(frozen=True, slots=True)
class VectorChunk:
    """A chunk vector and its source identifiers for a single version write."""

    chunk_id: UUID
    document_version_id: UUID
    knowledge_base_id: UUID
    embedding: Sequence[float]


@dataclass(frozen=True, slots=True)
class VectorSearchResult:
    """A scoped vector hit; callers must apply resource-state authorization."""

    chunk_id: UUID
    document_version_id: UUID
    knowledge_base_id: UUID
    score: float


class VectorStoreProvider(Protocol):
    async def replace_version_chunks(
        self,
        *,
        document_version_id: UUID,
        chunks: Sequence[VectorChunk],
    ) -> None: ...

    async def delete_version_chunks(self, *, document_version_id: UUID) -> None: ...

    async def search(
        self,
        *,
        knowledge_base_ids: Sequence[UUID],
        vector: Sequence[float],
        limit: int,
        project_id: UUID | None = None,
    ) -> list[VectorSearchResult]: ...
