"""Deterministic mock provider for local dev / tests (Phase 21).

Only used when ``MARKET_DATA_MOCK_MODE=true`` (or provider ``mock``). It never
runs as a silent production fallback — the manager surfaces ``provider=MOCK``
and the frontend shows a DEMO badge.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterable
from datetime import datetime, timezone
from decimal import Decimal

from app.market_data.models import Tick, to_decimal
from app.market_data.providers.base import MarketDataProvider
from app.market_data.symbols import IndexSymbol, get_index_universe

# Stable baseline prices for the demo feed (not live market values).
_BASELINES: dict[str, float] = {
    "NIFTY50": 25123.50,
    "BANKNIFTY": 57440.25,
    "MIDCAP100": 58420.55,
    "SMALLCAP100": 19840.25,
    "NIFTYIT": 41280.00,
    "NIFTYAUTO": 23890.40,
    "NIFTYFMCG": 58210.30,
    "INDIAVIX": 13.68,
}


class MockProvider(MarketDataProvider):
    name = "MOCK"

    def __init__(self, interval_seconds: float = 1.0, seed: int = 42) -> None:
        self._interval = interval_seconds
        self._seed = seed
        self._instruments: list[IndexSymbol] = list(get_index_universe())
        self._connected = False
        self._step = 0

    async def connect(self) -> None:
        self._connected = True

    async def disconnect(self) -> None:
        self._connected = False

    async def subscribe(self, instruments: Iterable[IndexSymbol]) -> None:
        self._instruments = list(instruments)

    async def unsubscribe(self, instruments: Iterable[IndexSymbol]) -> None:
        drop = {s.id for s in instruments}
        self._instruments = [s for s in self._instruments if s.id not in drop]

    def _price(self, sym: IndexSymbol, step: int) -> tuple[Decimal, Decimal]:
        """Deterministic (ltp, previous_close) for a symbol at a step."""
        base = _BASELINES.get(sym.id, 1000.0)
        previous_close = Decimal(str(round(base, 2)))
        # Deterministic pseudo-random drift from a stable hash (no RNG state).
        h = (hash((self._seed, sym.id, step)) % 2000) / 100000.0  # 0..0.02
        drift = Decimal(str(round(base * (h - 0.01), 2)))  # +-1%
        ltp = to_decimal(round(float(previous_close + drift), 2)) or previous_close
        return ltp, previous_close

    async def stream(self) -> AsyncIterator[Tick]:
        while self._connected:
            self._step += 1
            for sym in self._instruments:
                ltp, previous_close = self._price(sym, self._step)
                yield Tick(
                    symbol=sym.id,
                    display_name=sym.display_name,
                    exchange=sym.exchange,
                    provider=self.name,
                    ltp=ltp,
                    previous_close=previous_close,
                    timestamp=datetime.now(timezone.utc),
                )
            await asyncio.sleep(self._interval)
