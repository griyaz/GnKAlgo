"""Market WebSocket manager — Dhan live feed with dev mock fallback."""

import asyncio
import json
import logging
import random
from datetime import datetime, timezone

from fastapi import WebSocket

from app.brokers.dhan_feed_parser import PREV_CLOSE_PACKET, TICKER_PACKET
from app.brokers.dhan_market_feed import DhanMarketFeed
from app.config import settings
from app.database import AsyncSessionLocal
from app.services.candle_service import BASE_PRICES
from app.services.instrument_segments import dhan_exchange_segment, feed_key
from app.services.instrument_service import instrument_service
from app.services.market_quote_cache import bind_symbol, update_ltp, update_prev_close

logger = logging.getLogger(__name__)

# Frontend clients: key SYMBOL:EXCHANGE -> set of WebSocket
_client_subscribers: dict[str, set[WebSocket]] = {}

# Instrument subscription ref-count: feed_key -> count
_instrument_refcount: dict[str, int] = {}

# feed_key -> instrument metadata
_instrument_meta: dict[str, dict] = {}

# Per-user upstream Dhan connections
_user_feeds: dict[str, DhanMarketFeed] = {}
_user_creds: dict[str, dict] = {}

_mock_task: asyncio.Task | None = None
_mock_prices: dict[str, float] = {}


def _use_mock() -> bool:
  return settings.app_env != "production" or settings.debug


def _client_key(symbol: str, exchange: str) -> str:
  return f"{symbol.upper()}:{exchange.upper()}"


async def _resolve_instrument(symbol: str, exchange: str) -> dict | None:
    async with AsyncSessionLocal() as db:
        inst = await instrument_service.resolve(db, symbol, exchange)
        if inst:
            seg = inst.get("exchange_segment") or dhan_exchange_segment(
                inst.get("exchange", exchange), inst.get("segment", "EQUITY")
            )
            return {
                **inst,
                "dhan_segment": seg,
                "feed_key": feed_key(seg, inst["security_id"]),
            }
        fallback = instrument_service.curated_fallback(symbol)
        if fallback:
            seg = fallback.get("exchange_segment") or dhan_exchange_segment(
                fallback["exchange"], fallback["segment"]
            )
            return {
                **fallback,
                "dhan_segment": seg,
                "feed_key": feed_key(seg, fallback["security_id"]),
            }
    return None


async def _broadcast_to_clients(key: str, message: dict) -> None:
  sockets = _client_subscribers.get(key, set())
  if not sockets:
    return
  payload = json.dumps(message)
  dead: list[WebSocket] = []
  for ws in sockets:
    try:
      await ws.send_text(payload)
    except Exception:
      dead.append(ws)
  for ws in dead:
    sockets.discard(ws)


async def _on_dhan_tick(user_id: str, tick: dict) -> None:
  code = tick.get("response_code")
  seg = tick.get("exchange_segment", "")
  sid = tick.get("security_id", "")
  fk = feed_key(seg, sid)
  meta = _instrument_meta.get(fk)
  symbol = meta.get("symbol") if meta else None

  if code == PREV_CLOSE_PACKET and tick.get("prev_close") is not None:
    update_prev_close(seg, sid, float(tick["prev_close"]))
    return

  if code != TICKER_PACKET or tick.get("ltp") is None:
    return

  ltp = float(tick["ltp"])
  ltt = tick.get("ltt")
  volume = tick.get("volume")
  if symbol:
    bind_symbol(seg, sid, symbol)
  update_ltp(seg, sid, ltp, ltt=ltt, volume=volume, symbol=symbol)

  if not meta:
    return

  client_key = _client_key(meta["symbol"], meta.get("exchange", "NSE"))
  tick_time = int(ltt or datetime.now(timezone.utc).timestamp())
  await _broadcast_to_clients(
    client_key,
    {
      "type": "tick",
      "symbol": meta["symbol"],
      "exchange": meta.get("exchange", "NSE"),
      "ltp": ltp,
      "time": tick_time,
      "volume": volume,
      "source": "dhan",
    },
  )


async def _warm_index_subscriptions(feed: DhanMarketFeed) -> None:
    """Subscribe index instruments for ticker cache / header indices."""
    from sqlalchemy import select

    from app.models.instrument import Instrument

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Instrument).where(
                Instrument.is_active.is_(True),
                Instrument.segment == "INDEX",
                Instrument.exchange.in_(("NSE", "BSE")),
            )
        )
        index_rows = result.scalars().all()

    instruments = [
        (row.exchange_segment, row.security_id) for row in index_rows
    ]
    if instruments:
        await feed.subscribe(instruments)
        for row in index_rows:
            bind_symbol(row.exchange_segment, row.security_id, row.symbol)
            fk = feed_key(row.exchange_segment, row.security_id)
            _instrument_meta[fk] = {
                "symbol": row.symbol,
                "exchange": row.exchange,
                "segment": row.segment,
                "security_id": row.security_id,
                "exchange_segment": row.exchange_segment,
            }


async def _ensure_user_feed(user_id: str, creds: dict) -> DhanMarketFeed | None:
    if user_id in _user_feeds:
        return _user_feeds[user_id]

    access_token = creds.get("access_token") or creds.get("api_key")
    client_id = creds.get("client_id")
    if not access_token or not client_id:
        return None

    feed = DhanMarketFeed(access_token=access_token, client_id=client_id)
    try:
        await feed.connect(lambda t: _on_dhan_tick(user_id, t))
        _user_feeds[user_id] = feed
        _user_creds[user_id] = creds
        await _warm_index_subscriptions(feed)
        return feed
    except Exception as exc:
        logger.warning("Dhan feed connect failed for user %s: %s", user_id, exc)
        return None


async def _subscribe_upstream(user_id: str, inst: dict, creds: dict | None) -> bool:
  # Live ticks must be entitled per user. A global ref-count would let a
  # client without Dhan credentials join an instrument another user already
  # opened and receive that user's licensed feed.
  if not creds and not _use_mock():
    return False

  fk = inst["feed_key"]
  _instrument_meta[fk] = inst
  bind_symbol(inst["dhan_segment"], inst["security_id"], inst["symbol"])

  if _instrument_refcount.get(fk, 0) == 0:
    if creds:
      feed = await _ensure_user_feed(user_id, creds)
      if feed:
        await feed.subscribe([(inst["dhan_segment"], inst["security_id"])])
      elif not _use_mock():
        return False

  _instrument_refcount[fk] = _instrument_refcount.get(fk, 0) + 1
  return True


async def _unsubscribe_upstream(user_id: str, inst: dict) -> None:
  fk = inst["feed_key"]
  count = _instrument_refcount.get(fk, 0)
  if count <= 1:
    _instrument_refcount.pop(fk, None)
    _instrument_meta.pop(fk, None)
    creds = _user_creds.get(user_id)
    if creds and user_id in _user_feeds:
      await _user_feeds[user_id].unsubscribe([(inst["dhan_segment"], inst["security_id"])])
  else:
    _instrument_refcount[fk] = count - 1


async def _mock_broadcast_loop() -> None:
  while True:
    for key, sockets in list(_client_subscribers.items()):
      if not sockets:
        continue
      symbol = key.split(":")[0]
      base = _mock_prices.get(key, BASE_PRICES.get(symbol, 1000.0))
      drift = random.uniform(-0.002, 0.002) * base
      price = round(base + drift, 2)
      _mock_prices[key] = price
      msg = json.dumps(
        {
          "type": "tick",
          "symbol": symbol,
          "ltp": price,
          "time": int(datetime.now(timezone.utc).timestamp()),
          "source": "mock_dev",
        }
      )
      dead: list[WebSocket] = []
      for ws in sockets:
        try:
          await ws.send_text(msg)
        except Exception:
          dead.append(ws)
      for ws in dead:
        sockets.discard(ws)
    await asyncio.sleep(1.5)


def _start_mock_if_needed() -> None:
  global _mock_task
  if _use_mock() and (_mock_task is None or _mock_task.done()):
    _mock_task = asyncio.create_task(_mock_broadcast_loop())


async def subscribe_ws(
  ws: WebSocket,
  user_id: str,
  symbol: str,
  exchange: str,
  dhan_creds: dict | None,
) -> None:
  inst = await _resolve_instrument(symbol, exchange)
  if not inst:
    await ws.send_text(json.dumps({"type": "error", "message": "Instrument not found"}))
    return

  client_key = _client_key(inst["symbol"], inst.get("exchange", exchange))
  ok = await _subscribe_upstream(user_id, inst, dhan_creds)
  if not ok:
    await ws.send_text(
      json.dumps(
        {
          "type": "error",
          "message": "Connect Dhan to access live market data.",
          "code": "BROKER_REQUIRED",
        }
      )
    )
    return

  if client_key not in _client_subscribers:
    _client_subscribers[client_key] = set()
  _client_subscribers[client_key].add(ws)

  if dhan_creds is None and _use_mock():
    _start_mock_if_needed()

  await ws.send_text(
    json.dumps(
      {
        "type": "subscribed",
        "symbol": inst["symbol"],
        "exchange": inst.get("exchange", exchange),
        "live": dhan_creds is not None,
        "source": "dhan" if dhan_creds else "mock_dev",
      }
    )
  )


async def unsubscribe_ws(ws: WebSocket, user_id: str, symbol: str, exchange: str) -> None:
  inst = await _resolve_instrument(symbol, exchange)
  if not inst:
    return
  client_key = _client_key(inst["symbol"], inst.get("exchange", exchange))
  if client_key in _client_subscribers:
    _client_subscribers[client_key].discard(ws)
    if not _client_subscribers[client_key]:
      del _client_subscribers[client_key]
      await _unsubscribe_upstream(user_id, inst)


async def unsubscribe_all(ws: WebSocket, user_id: str) -> None:
  for key in list(_client_subscribers.keys()):
    if ws in _client_subscribers.get(key, set()):
      symbol, exchange = key.split(":", 1)
      await unsubscribe_ws(ws, user_id, symbol, exchange)
