"""Market-data provider contract for prices and instrument metadata."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol


class MarketDataProvider(Protocol):
    async def latest_prices(self, symbols: Sequence[str]) -> dict[str, float]: ...
