"""Upstox Market Data Feed V3 provider (optional fallback).

Uses the official ``upstox-python-sdk`` ``MarketDataStreamerV3`` when installed
(V3 only — never the deprecated V1/V2 feeds). The SDK decodes the protobuf feed
into a dict which is normalized here into :class:`Tick`. The SDK is optional and
not installed by default; enable with ``UPSTOX_MARKET_DATA_ENABLED=true`` and add
``upstox-python-sdk`` to the backend requirements.

This provider is market-data only and does not touch any existing Upstox
historical-candle logic.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Iterable
from datetime import datetime, timezone

from app.config import settings
from app.market_data.models import Tick, to_decimal
from app.market_data.providers.base import (
    MarketDataProvider,
    ProviderAuthError,
    ProviderUnavailable,
)
from app.market_data.symbols import IndexSymbol, by_upstox_key, get_index_universe

logger = logging.getLogger(__name__)

_CLOSED = object()


class UpstoxProvider(MarketDataProvider):
    name = "UPSTOX"

    def __init__(self, access_token: str | None = None) -> None:
        self._access_token = (
            access_token if access_token is not None else settings.upstox_access_token
        )
        self._streamer = None
        self._queue: asyncio.Queue = asyncio.Queue(maxsize=10000)
        self._loop: asyncio.AbstractEventLoop | None = None
        self._instruments: list[IndexSymbol] = list(get_index_universe())
        self._connected = False

    def _push(self, item) -> None:
        loop = self._loop
        if loop is None:
            return
        try:
            loop.call_soon_threadsafe(self._queue.put_nowait, item)
        except (asyncio.QueueFull, RuntimeError):
            pass

    async def connect(self) -> None:
        if not settings.upstox_market_data_enabled:
            raise ProviderUnavailable(
                "Upstox market data is disabled (UPSTOX_MARKET_DATA_ENABLED=false)"
            )
        if not self._access_token:
            raise ProviderAuthError("UPSTOX_ACCESS_TOKEN is required")
        try:
            import upstox_client  # type: ignore
        except ImportError as exc:  # pragma: no cover - optional dep
            raise ProviderUnavailable(
                "upstox-python-sdk is not installed; add it to requirements to use Upstox V3"
            ) from exc

        self._loop = asyncio.get_running_loop()
        configuration = upstox_client.Configuration()
        configuration.access_token = self._access_token
        instrument_keys = [s.upstox for s in self._instruments]
        logger.info("market_data.provider.connecting provider=UPSTOX")
        # V3 market-data streamer (LTPC mode keeps LTP + close price light).
        self._streamer = upstox_client.MarketDataStreamerV3(
            upstox_client.ApiClient(configuration),
            instrument_keys,
            "ltpc",
        )
        self._streamer.on("message", self._on_message)
        self._streamer.on("error", self._on_error)
        self._streamer.on("close", lambda *_: self._push(_CLOSED))
        self._streamer.connect()
        self._connected = True
        logger.info("market_data.provider.connected provider=UPSTOX")

    def _on_message(self, message) -> None:
        self._push(message)

    def _on_error(self, error) -> None:
        logger.warning("market_data.provider.error provider=UPSTOX detail=%s", error)

    async def disconnect(self) -> None:
        self._connected = False
        if self._streamer is not None:
            try:
                self._streamer.disconnect()
            except Exception:  # pragma: no cover
                pass
            self._streamer = None

    async def subscribe(self, instruments: Iterable[IndexSymbol]) -> None:
        self._instruments = list(instruments)
        if self._streamer is not None:
            try:
                self._streamer.subscribe([s.upstox for s in self._instruments], "ltpc")
            except Exception as exc:  # pragma: no cover
                logger.warning("market_data.subscription.failure provider=UPSTOX error=%s", exc)

    async def unsubscribe(self, instruments: Iterable[IndexSymbol]) -> None:
        if self._streamer is not None:
            try:
                self._streamer.unsubscribe([s.upstox for s in instruments])
            except Exception as exc:  # pragma: no cover
                logger.warning("market_data.provider.error provider=UPSTOX error=%s", exc)

    def normalize(self, message: dict) -> list[Tick]:
        """Map an Upstox V3 feed message into Ticks.

        Expected shape: ``{"feeds": {"<key>": {"ltpc": {"ltp": .., "cp": ..}}}}``.
        """
        ticks: list[Tick] = []
        if not isinstance(message, dict):
            return ticks
        feeds = message.get("feeds") or {}
        for key, feed in feeds.items():
            sym = by_upstox_key(key)
            if sym is None:
                continue
            ltpc = (feed or {}).get("ltpc") or {}
            ltp = to_decimal(ltpc.get("ltp"))
            prev_close = to_decimal(ltpc.get("cp"))
            if ltp is None and prev_close is None:
                continue
            ticks.append(
                Tick(
                    symbol=sym.id,
                    display_name=sym.display_name,
                    exchange=sym.exchange,
                    provider=self.name,
                    ltp=ltp,
                    previous_close=prev_close,
                    timestamp=datetime.now(timezone.utc),
                )
            )
        return ticks

    async def stream(self) -> AsyncIterator[Tick]:
        while self._connected:
            item = await self._queue.get()
            if item is _CLOSED:
                return
            for tick in self.normalize(item):
                yield tick
