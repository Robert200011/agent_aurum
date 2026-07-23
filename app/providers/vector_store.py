"""Vector-store provider contract kept independent from a concrete database."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol


class VectorStoreProvider(Protocol):
    async def search(
        self,
        *,
        knowledge_base_ids: Sequence[str],
        vector: Sequence[float],
        limit: int,
    ) -> list[dict[str, object]]: ...
