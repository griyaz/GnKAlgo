"""LiveMarketTicker API — REST snapshot/health + internal WebSocket.

Routes:
    GET  /api/v1/market/ticker   cached ticker snapshot
    GET  /api/v1/market/health   feed/provider/redis health
    WS   /ws/market/ticker       snapshot + live fan-out (Redis pub/sub or local)

The frontend keeps a single WebSocket to ``/ws/market/ticker``; the backend owns
the one upstream provider connection. No provider credentials are ever sent to
the client.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.config import settings
from app.database import AsyncSessionLocal
from app.market_data import store
from app.market_data.manager import market_manager
from app.market_data.symbols import get_index_universe

logger = logging.getLogger(__name__)

# REST endpoints live under the existing /api/v1/market prefix.
router = APIRouter(prefix="/market", tags=["Market Ticker"])
# WebSocket lives at the app root: /ws/market/ticker
ws_router = APIRouter()

# Basic connection-limit protection (Phase 17).
MAX_TICKER_CLIENTS = 1000
_active_clients = 0


def _ordered(data: list[dict]) -> list[dict]:
    order = {s.id: i for i, s in enumerate(get_index_universe())}
    return sorted(data, key=lambda d: order.get(d.get("symbol", ""), 999))


async def _snapshot_message() -> dict:
    data = await store.get_snapshot()
    if not data:
        data = market_manager.local_snapshot()
    meta = await store.get_meta() or market_manager.meta_snapshot()
    return {
        "type": "snapshot",
        "provider": meta.get("provider", "NONE"),
        "market_status": meta.get("market_status", "UNKNOWN"),
        "demo": meta.get("demo", False),
        "stale": meta.get("stale", False),
        "server_time": datetime.now(timezone.utc).isoformat(),
        "data": _ordered(data),
    }


@router.get("/ticker")
async def market_ticker_snapshot():
    """Current cached ticker snapshot (used for the initial paint)."""
    return await _snapshot_message()


@router.get("/health")
async def market_ticker_health():
    return await market_manager.health()


# ---------------------------------------------------------------------------
# WebSocket
# ---------------------------------------------------------------------------
def _origin_allowed(ws: WebSocket) -> bool:
    origin = ws.headers.get("origin")
    if not origin:
        # Non-browser client (curl/websocat) — allowed; auth still applies.
        return True
    allowed = settings.origins_list
    if origin in allowed:
        return True
    # Accept any *.gnkalgo.com origin (matches CORS policy).
    return origin.endswith(".gnkalgo.com") or origin.rstrip("/").endswith("gnkalgo.com")


async def _authenticate(ws: WebSocket) -> bool:
    if not settings.market_data_require_auth:
        return True
    token = ws.cookies.get("gnk_access")
    if not token:
        # Allow a first-message auth without putting the token in the URL.
        try:
            first = await asyncio.wait_for(ws.receive_text(), timeout=5)
            payload = json.loads(first)
            if isinstance(payload, dict) and payload.get("action") == "auth":
                token = payload.get("token") or ws.cookies.get("gnk_access")
        except Exception:
            token = None
    if not token:
        return False
    from app.core.deps import user_from_access_token

    async with AsyncSessionLocal() as db:
        try:
            await user_from_access_token(db, token)
            await db.commit()
            return True
        except Exception:
            return False


@ws_router.websocket("/ws/market/ticker")
async def market_ticker_ws(ws: WebSocket):
    global _active_clients
    if not _origin_allowed(ws):
        await ws.close(code=4403)
        return
    await ws.accept()

    if not await _authenticate(ws):
        await ws.close(code=4401)
        return

    if _active_clients >= MAX_TICKER_CLIENTS:
        await ws.close(code=1013)  # try again later
        return
    _active_clients += 1

    use_redis = await store.redis_healthy()
    local_queue = None if use_redis else market_manager.subscribe_local()
    try:
        # 1. Immediate snapshot.
        await ws.send_text(json.dumps(await _snapshot_message()))

        # 2. Fan-out + keepalive + disconnect detection run concurrently.
        forward = asyncio.create_task(_forward(ws, use_redis, local_queue))
        receiver = asyncio.create_task(_receive(ws))
        done, pending = await asyncio.wait(
            {forward, receiver}, return_when=asyncio.FIRST_COMPLETED
        )
        for task in pending:
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
    except WebSocketDisconnect:
        pass
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug("market_data.ws.error error=%s", exc)
    finally:
        _active_clients -= 1
        if local_queue is not None:
            market_manager.unsubscribe_local(local_queue)
        try:
            await ws.close()
        except Exception:
            pass


async def _forward(ws: WebSocket, use_redis: bool, local_queue) -> None:
    if use_redis:
        async for message in store.subscribe_updates():
            await ws.send_text(json.dumps(message))
    else:
        while True:
            message = await local_queue.get()
            await ws.send_text(json.dumps(message))


async def _receive(ws: WebSocket) -> None:
    """Drain client messages (e.g. pings) and detect disconnects."""
    while True:
        try:
            await ws.receive_text()
        except WebSocketDisconnect:
            return
