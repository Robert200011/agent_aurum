"""Finance-data provider contract for future internal or external integrations."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol
from uuid import UUID


class FinanceDataProvider(Protocol):
    async def list_accounts(self, user_id: UUID) -> Sequence[dict[str, object]]: ...
