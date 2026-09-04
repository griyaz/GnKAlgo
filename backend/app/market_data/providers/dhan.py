"""Dhan market-feed provider (optional fallback).

Reuses the project's existing :class:`~app.brokers.dhan_market_feed.DhanMarketFeed`
and binary parser rather than re-implementing packet decoding. This is the
*market data* path only and uses dedicated ``DHAN_*`` market-data credentials —
it does not touch Dhan order/execution logic.

Dhan sends LTP and previous-close in separate packets, so partial ticks are
yielded and merged by the manager (see ``Tick.merged_with``).
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Iterable
from datetime import datetime, timezone

from app.brokers.dhan_feed_parser import PREV_CLOSE_PACKET, TICKER_PACKET
from app.config import settings
from app.market_data.models import Tick, to_decimal
from app.market_data.providers.base import (
    MarketDataProvider,
    ProviderAuthError,
    ProviderUnavailable,
)
from app.market_data.symbols import IndexSymbol, by_dhan_key, get_index_universe

logger = logging.getLogger(__name__)

_CLOSED = object()


class DhanProvider(MarketDataProvider):
    name = "DHAN"

    def __init__(self, client_id: str | None = None, access_token: str | None = None) -> None:
        self._client_id = client_id if client_id is not None else settings.dhan_client_id
        self._access_token = (
            access_token if access_token is not None else settings.dhan_access_token
        )
        self._feed = None
        self._queue: asyncio.Queue = asyncio.Queue(maxsize=10000)
        self._watcher: asyncio.Task | None = None
        self._instruments: list[IndexSymbol] = list(get_index_universe())
        self._connected = False

    async def _handle(self, packet: dict) -> None:
        tick = self.normalize(packet)
        if tick is not None:
            try:
                self._queue.put_nowait(tick)
            except asyncio.QueueFull:
                pass

    async def connect(self) -> None:
        if not settings.dhan_market_data_enabled:
            raise ProviderUnavailable("Dhan market data is disabled (DHAN_MARKET_DATA_ENABLED=false)")
        if not self._access_token or not self._client_id:
            raise ProviderAuthError("DHAN_CLIENT_ID and DHAN_ACCESS_TOKEN are required")
        try:
            from app.brokers.dhan_market_feed import DhanMarketFeed
        except ImportError as exc:  # pragma: no cover
            raise ProviderUnavailable("Dhan market feed client unavailable") from exc

        logger.info("market_data.provider.connecting provider=DHAN")
        self._feed = DhanMarketFeed(
            access_token=self._access_token, client_id=self._client_id
        )
        await self._feed.connect(self._handle)
        self._connected = True
        self._watcher = asyncio.create_task(self._watch_closed())
        logger.info("market_data.provider.connected provider=DHAN")

    async def _watch_closed(self) -> None:
        reader = getattr(self._feed, "_reader_task", None)
        if reader is None:
            return
        try:
            await reader
        except asyncio.CancelledError:  # pragma: no cover
            return
        finally:
            try:
                self._queue.put_nowait(_CLOSED)
            except asyncio.QueueFull:  # pragma: no cover
                pass

    async def disconnect(self) -> None:
        self._connected = False
        if self._watcher:
            self._watcher.cancel()
            self._watcher = None
        if self._feed is not None:
            try:
                await self._feed.close()
            except Exception:  # pragma: no cover
                pass
            self._feed = None

    async def subscribe(self, instruments: Iterable[IndexSymbol]) -> None:
        self._instruments = list(instruments)
        if self._feed is not None:
            pairs = [(s.dhan_segment, s.dhan_security_id) for s in self._instruments]
            await self._feed.subscribe(pairs)
            logger.info(
                "market_data.subscription.success provider=DHAN count=%d", len(pairs)
            )

    async def unsubscribe(self, instruments: Iterable[IndexSymbol]) -> None:
        if self._feed is not None:
            pairs = [(s.dhan_segment, s.dhan_security_id) for s in instruments]
            await self._feed.unsubscribe(pairs)

    def normalize(self, packet: dict) -> Tick | None:
        seg = packet.get("exchange_segment", "")
        sid = str(packet.get("security_id", ""))
        sym = by_dhan_key(seg, sid)
        if sym is None:
            return None
        code = packet.get("response_code")
        ltp = to_decimal(packet.get("ltp"))
        prev_close = to_decimal(packet.get("prev_close"))
        if code == PREV_CLOSE_PACKET and prev_close is None:
            return None
        if code == TICKER_PACKET and ltp is None:
            return None
        ltt = packet.get("ltt")
        try:
            timestamp = (
                datetime.fromtimestamp(int(ltt), tz=timezone.utc)
                if ltt
                else datetime.now(timezone.utc)
            )
        except (ValueError, TypeError, OSError):
            timestamp = datetime.now(timezone.utc)
        return Tick(
            symbol=sym.id,
            display_name=sym.display_name,
            exchange=sym.exchange,
            provider=self.name,
            ltp=ltp,
            previous_close=prev_close,
            timestamp=timestamp,
        )

    async def stream(self) -> AsyncIterator[Tick]:
        while self._connected:
            item = await self._queue.get()
            if item is _CLOSED:
                return
            yield item
