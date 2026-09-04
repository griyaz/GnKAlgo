"""Redis latest-price cache and pub/sub fan-out for the ticker.

Keys:
    market:ticker:<INDEX_ID>   JSON snapshot per index (TTL while market open)
    market:ticker:meta         JSON provider/market-status/last-update metadata

Channel:
    market:ticker:updates      JSON ticker_update messages (pub/sub fan-out)

Every FastAPI worker can serve the ticker WebSocket by reading these keys and
subscribing to the channel; only the single feed-owner worker writes them, so
we never need one upstream provider connection per worker.
"""

from __future__ import annotations

import json
import logging
from typing import Any, AsyncIterator

from app.services.redis_cache import get_redis

logger = logging.getLogger(__name__)

KEY_PREFIX = "market:ticker:"
META_KEY = "market:ticker:meta"
UPDATES_CHANNEL = "market:ticker:updates"


def _key(index_id: str) -> str:
    return f"{KEY_PREFIX}{index_id}"


async def save_tick(index_id: str, payload: dict[str, Any], ttl_seconds: int) -> None:
    client = await get_redis()
    if not client:
        return
    try:
        await client.set(_key(index_id), json.dumps(payload), ex=max(ttl_seconds, 1))
    except Exception as exc:  # pragma: no cover - redis runtime
        logger.debug("market_data.store.save_failed id=%s error=%s", index_id, exc)


async def save_meta(meta: dict[str, Any], ttl_seconds: int) -> None:
    client = await get_redis()
    if not client:
        return
    try:
        await client.set(META_KEY, json.dumps(meta), ex=max(ttl_seconds, 1))
    except Exception:  # pragma: no cover
        pass


async def get_meta() -> dict[str, Any] | None:
    client = await get_redis()
    if not client:
        return None
    try:
        raw = await client.get(META_KEY)
        return json.loads(raw) if raw else None
    except Exception:  # pragma: no cover
        return None


async def get_snapshot() -> list[dict[str, Any]]:
    """Return all cached index snapshots (unordered)."""
    client = await get_redis()
    if not client:
        return []
    try:
        keys = [k async for k in client.scan_iter(match=f"{KEY_PREFIX}*")]
        keys = [k for k in keys if k != META_KEY]
        if not keys:
            return []
        values = await client.mget(keys)
        out: list[dict[str, Any]] = []
        for raw in values:
            if raw:
                try:
                    out.append(json.loads(raw))
                except json.JSONDecodeError:
                    continue
        return out
    except Exception:  # pragma: no cover
        return []


async def publish_update(message: dict[str, Any]) -> None:
    client = await get_redis()
    if not client:
        return
    try:
        await client.publish(UPDATES_CHANNEL, json.dumps(message))
    except Exception as exc:  # pragma: no cover
        logger.debug("market_data.store.publish_failed error=%s", exc)


async def subscribe_updates() -> AsyncIterator[dict[str, Any]]:
    """Yield decoded messages published to the updates channel.

    Falls back to no messages (returns) when Redis is unavailable so the WS
    endpoint can still serve the initial snapshot.
    """
    client = await get_redis()
    if not client:
        return
    pubsub = client.pubsub()
    await pubsub.subscribe(UPDATES_CHANNEL)
    try:
        async for message in pubsub.listen():
            if message is None or message.get("type") != "message":
                continue
            data = message.get("data")
            if not data:
                continue
            try:
                yield json.loads(data)
            except (json.JSONDecodeError, TypeError):
                continue
    finally:
        try:
            await pubsub.unsubscribe(UPDATES_CHANNEL)
            await pubsub.aclose()
        except Exception:  # pragma: no cover
            pass


async def redis_healthy() -> bool:
    client = await get_redis()
    if not client:
        return False
    try:
        await client.ping()
        return True
    except Exception:  # pragma: no cover
        return False
