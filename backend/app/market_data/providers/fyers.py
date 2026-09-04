"""FYERS API v3 WebSocket provider (primary).

Uses the official ``fyers-apiv3`` SDK's ``FyersDataSocket`` when installed. The
SDK is threaded/callback-based, so its callbacks are bridged onto an
``asyncio.Queue`` consumed by :meth:`stream`. Reconnect/backoff is owned by the
manager (SDK ``reconnect=False``) so all providers share one policy.

Credentials are backend-only (``FYERS_CLIENT_ID`` / ``FYERS_ACCESS_TOKEN``) and
are never logged or sent to the client.
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
from app.market_data.symbols import IndexSymbol, by_fyers_symbol, get_index_universe

logger = logging.getLogger(__name__)

# Sentinel pushed when the upstream socket closes so stream() ends cleanly.
_CLOSED = object()


class FyersProvider(MarketDataProvider):
    name = "FYERS"

    def __init__(self, client_id: str | None = None, access_token: str | None = None) -> None:
        self._client_id = client_id if client_id is not None else settings.fyers_client_id
        self._access_token = (
            access_token if access_token is not None else settings.fyers_access_token
        )
        self._socket = None
        self._queue: asyncio.Queue = asyncio.Queue(maxsize=10000)
        self._loop: asyncio.AbstractEventLoop | None = None
        self._instruments: list[IndexSymbol] = list(get_index_universe())
        self._connected = False

    # -- auth token ----------------------------------------------------
    def _auth_token(self) -> str:
        """FYERS data socket expects ``APPID:ACCESS_TOKEN``.

        If ``FYERS_ACCESS_TOKEN`` already contains the combined form we use it
        as-is; otherwise we join it with ``FYERS_CLIENT_ID``.
        """
        token = (self._access_token or "").strip()
        if ":" in token:
            return token
        if not token or not self._client_id:
            raise ProviderAuthError("FYERS_CLIENT_ID and FYERS_ACCESS_TOKEN are required")
        return f"{self._client_id}:{token}"

    # -- threadsafe callback bridge -----------------------------------
    def _push(self, item) -> None:
        loop = self._loop
        if loop is None:
            return
        try:
            loop.call_soon_threadsafe(self._queue.put_nowait, item)
        except (asyncio.QueueFull, RuntimeError):
            pass

    def _on_message(self, message) -> None:
        self._push(message)

    def _on_error(self, message) -> None:
        logger.warning("market_data.provider.error provider=FYERS detail=%s", message)

    def _on_close(self, message) -> None:
        logger.info("market_data.provider.disconnected provider=FYERS")
        self._push(_CLOSED)

    def _on_open(self) -> None:
        # Subscribe to the full universe once the socket is open.
        symbols = [s.fyers for s in self._instruments]
        try:
            self._socket.subscribe(symbols=symbols, data_type="SymbolUpdate")
            self._socket.keep_running()
            logger.info(
                "market_data.subscription.success provider=FYERS count=%d", len(symbols)
            )
        except Exception as exc:  # pragma: no cover - SDK runtime
            logger.warning("market_data.subscription.failure provider=FYERS error=%s", exc)

    async def connect(self) -> None:
        try:
            from fyers_apiv3.FyersWebsocket import data_ws  # type: ignore
        except ImportError as exc:  # pragma: no cover - optional dep
            raise ProviderUnavailable(
                "fyers-apiv3 is not installed; add it to requirements to use FYERS"
            ) from exc

        self._loop = asyncio.get_running_loop()
        access = self._auth_token()
        self._socket = data_ws.FyersDataSocket(
            access_token=access,
            log_path="",
            litemode=False,  # full SymbolUpdate gives prev_close reliably
            write_to_file=False,
            reconnect=False,  # manager owns reconnect/backoff
            on_connect=self._on_open,
            on_close=self._on_close,
            on_error=self._on_error,
            on_message=self._on_message,
        )
        logger.info("market_data.provider.connecting provider=FYERS")
        # SDK connect() spawns its own thread and returns.
        self._socket.connect()
        self._connected = True
        logger.info("market_data.provider.connected provider=FYERS")

    async def disconnect(self) -> None:
        self._connected = False
        if self._socket is not None:
            try:
                self._socket.close_connection()
            except Exception:  # pragma: no cover - SDK runtime
                pass
            self._socket = None

    async def subscribe(self, instruments: Iterable[IndexSymbol]) -> None:
        self._instruments = list(instruments)
        if self._socket is not None:
            try:
                self._socket.subscribe(
                    symbols=[s.fyers for s in self._instruments], data_type="SymbolUpdate"
                )
            except Exception as exc:  # pragma: no cover
                logger.warning("market_data.subscription.failure provider=FYERS error=%s", exc)

    async def unsubscribe(self, instruments: Iterable[IndexSymbol]) -> None:
        if self._socket is not None:
            try:
                self._socket.unsubscribe(
                    symbols=[s.fyers for s in instruments], data_type="SymbolUpdate"
                )
            except Exception as exc:  # pragma: no cover
                logger.warning("market_data.provider.error provider=FYERS error=%s", exc)

    def normalize(self, message: dict) -> Tick | None:
        """Map a FYERS SymbolUpdate message into a :class:`Tick`."""
        if not isinstance(message, dict):
            return None
        raw_symbol = message.get("symbol") or message.get("symbol_ticker")
        if not raw_symbol:
            return None
        sym = by_fyers_symbol(raw_symbol)
        if sym is None:
            return None
        ltp = to_decimal(message.get("ltp"))
        prev_close = to_decimal(
            message.get("prev_close_price")
            if message.get("prev_close_price") is not None
            else message.get("prev_close")
        )
        feed_time = message.get("exch_feed_time") or message.get("last_traded_time")
        try:
            timestamp = (
                datetime.fromtimestamp(int(feed_time), tz=timezone.utc)
                if feed_time
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
            open=to_decimal(message.get("open_price")),
            high=to_decimal(message.get("high_price")),
            low=to_decimal(message.get("low_price")),
            timestamp=timestamp,
        )

    async def stream(self) -> AsyncIterator[Tick]:
        while self._connected:
            item = await self._queue.get()
            if item is _CLOSED:
                return
            tick = self.normalize(item)
            if tick is not None:
                yield tick
