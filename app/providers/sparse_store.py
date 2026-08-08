"""Sparse retrieval contracts independent from the PostgreSQL implementation."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID


@dataclass(frozen=True, slots=True)
class SparseSearchResult:
    """A user-scoped keyword hit and its database similarity score."""

    chunk_id: UUID
    document_version_id: UUID
    knowledge_base_id: UUID
    score: float


class SparseStoreProvider(Protocol):
    async def search(
        self,
        *,
        knowledge_base_ids: Sequence[UUID],
        query: str,
        limit: int,
        owner_user_id: UUID,
    ) -> list[SparseSearchResult]: ...
