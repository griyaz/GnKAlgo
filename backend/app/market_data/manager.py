"""MarketDataManager — owns the single upstream connection and fan-out.

Responsibilities (Phase 8):
* select the configured primary provider (or mock), with gated failover;
* keep exactly one upstream connection even across multiple FastAPI workers,
  using a Redis leader-lock (falls back to in-process ownership without Redis);
* normalize ticks, apply market status + stale detection;
* write the latest price per index to Redis and publish updates via pub/sub;
* expose health for ``GET /api/v1/market/health``.

Tick payloads NEVER contain provider credentials.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from time import monotonic

from app.config import settings
from app.market_data import store
from app.market_data.market_status import compute_market_status, status_label
from app.market_data.models import MarketStatus, Tick
from app.market_data.providers.base import (
    BackoffPolicy,
    MarketDataProvider,
    ProviderAuthError,
    ProviderUnavailable,
)
from app.market_data.symbols import get_index_universe
from app.services.redis_cache import get_redis

logger = logging.getLogger(__name__)

LEADER_KEY = "market:ticker:leader"
LEADER_TTL_SECONDS = 15
LEADER_RENEW_SECONDS = 5


def should_mark_stale(
    status: MarketStatus,
    last_update_monotonic: float | None,
    now_monotonic: float,
    threshold_seconds: float,
) -> bool:
    """Pure stale decision: only stale while OPEN and past the threshold."""
    if status != MarketStatus.OPEN or last_update_monotonic is None:
        return False
    return (now_monotonic - last_update_monotonic) > threshold_seconds


def _build_provider(name: str) -> MarketDataProvider:
    name = (name or "").lower()
    if name == "mock":
        from app.market_data.providers.mock import MockProvider

        return MockProvider()
    if name == "fyers":
        from app.market_data.providers.fyers import FyersProvider

        return FyersProvider()
    if name == "dhan":
        from app.market_data.providers.dhan import DhanProvider

        return DhanProvider()
    if name == "upstox":
        from app.market_data.providers.upstox import UpstoxProvider

        return UpstoxProvider()
    raise ProviderUnavailable(f"Unknown market data provider: {name}")


class MarketDataManager:
    def __init__(self) -> None:
        self._task: asyncio.Task | None = None
        self._running = False
        self._is_leader = False
        self._leader_token = uuid.uuid4().hex

        self._provider: MarketDataProvider | None = None
        self._provider_name = "NONE"
        self._connected = False
        self._status = MarketStatus.UNKNOWN
        self._stale = False

        self._ticks: dict[str, Tick] = {}
        self._last_update_monotonic: float | None = None
        self._last_tick_at: datetime | None = None

        # In-process fan-out for WS clients on the same worker (and the only
        # path when Redis is unavailable in single-worker dev).
        self._local_subscribers: set[asyncio.Queue] = set()

    # -- lifecycle -----------------------------------------------------
    def start(self) -> None:
        if self._task and not self._task.done():
            return
        self._running = True
        self._task = asyncio.create_task(self._supervise())

    async def stop(self) -> None:
        self._running = False
        if self._provider is not None:
            try:
                await self._provider.disconnect()
            except Exception:  # pragma: no cover
                pass
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        await self._release_leadership()

    # -- demo / provider selection ------------------------------------
    @property
    def demo_mode(self) -> bool:
        return settings.market_data_mock_mode or settings.market_data_provider.lower() == "mock"

    def _provider_candidates(self) -> list[str]:
        if self.demo_mode:
            return ["mock"]
        primary = settings.market_data_provider.lower()
        candidates = [primary]
        if settings.market_data_failover_enabled:
            if settings.dhan_market_data_enabled and "dhan" not in candidates:
                candidates.append("dhan")
            if settings.upstox_market_data_enabled and "upstox" not in candidates:
                candidates.append("upstox")
        return candidates

    # -- leadership (single upstream owner) ---------------------------
    async def _acquire_leadership(self) -> bool:
        client = await get_redis()
        if client is None:
            # No Redis: this process owns the feed (single-worker dev).
            self._is_leader = True
            return True
        try:
            ok = await client.set(
                LEADER_KEY, self._leader_token, nx=True, ex=LEADER_TTL_SECONDS
            )
            self._is_leader = bool(ok)
            return self._is_leader
        except Exception:  # pragma: no cover
            self._is_leader = True
            return True

    async def _renew_leadership(self) -> bool:
        client = await get_redis()
        if client is None:
            return True
        try:
            current = await client.get(LEADER_KEY)
            if current != self._leader_token:
                self._is_leader = False
                return False
            await client.set(LEADER_KEY, self._leader_token, ex=LEADER_TTL_SECONDS)
            return True
        except Exception:  # pragma: no cover
            return True

    async def _release_leadership(self) -> None:
        client = await get_redis()
        if client is None or not self._is_leader:
            self._is_leader = False
            return
        try:
            current = await client.get(LEADER_KEY)
            if current == self._leader_token:
                await client.delete(LEADER_KEY)
        except Exception:  # pragma: no cover
            pass
        self._is_leader = False

    # -- main supervisor ----------------------------------------------
    async def _supervise(self) -> None:
        while self._running:
            got = await self._acquire_leadership()
            if not got:
                # Another worker owns the upstream; idle and retry.
                await asyncio.sleep(LEADER_RENEW_SECONDS)
                continue
            try:
                await self._run_as_leader()
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # pragma: no cover - defensive
                logger.exception("market_data.manager.crashed error=%s", exc)
                await asyncio.sleep(2)
            finally:
                await self._release_leadership()

    async def _run_as_leader(self) -> None:
        universe = list(get_index_universe())
        backoff = BackoffPolicy()
        candidates = self._provider_candidates()
        idx = 0
        self._status = compute_market_status()

        stale_task = asyncio.create_task(self._status_and_stale_loop())
        renew_task = asyncio.create_task(self._leadership_renew_loop())
        try:
            while self._running and self._is_leader:
                name = candidates[idx]
                provider = _build_provider(name)
                self._provider = provider
                self._provider_name = provider.name
                stable_since: float | None = None
                try:
                    logger.info("market_data.provider.connecting provider=%s", provider.name)
                    await provider.connect()
                    await provider.subscribe(universe)
                    self._connected = True
                    stable_since = monotonic()
                    await self._publish_provider_status()
                    async for tick in provider.stream():
                        if not (self._running and self._is_leader):
                            break
                        await self._on_tick(tick)
                except (ProviderUnavailable, ProviderAuthError) as exc:
                    logger.warning(
                        "market_data.provider.unavailable provider=%s reason=%s",
                        name,
                        exc,
                    )
                    if settings.market_data_failover_enabled and len(candidates) > 1:
                        prev = candidates[idx]
                        idx = (idx + 1) % len(candidates)
                        logger.warning(
                            "market_data.failover primary=%s fallback=%s reason=%s at=%s",
                            prev,
                            candidates[idx],
                            exc,
                            datetime.now(timezone.utc).isoformat(),
                        )
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    logger.warning(
                        "market_data.provider.error provider=%s error=%s", name, exc
                    )
                finally:
                    self._connected = False
                    try:
                        await provider.disconnect()
                    except Exception:  # pragma: no cover
                        pass
                    self._provider = None

                if not (self._running and self._is_leader):
                    break
                if stable_since is not None and (
                    monotonic() - stable_since >= backoff.stable_after_seconds
                ):
                    backoff.reset()
                delay = backoff.next_delay()
                logger.info(
                    "market_data.provider.reconnecting provider=%s in=%.1fs", name, delay
                )
                await self._publish_provider_status()
                await asyncio.sleep(delay)
        finally:
            stale_task.cancel()
            renew_task.cancel()
            for t in (stale_task, renew_task):
                try:
                    await t
                except (asyncio.CancelledError, Exception):  # pragma: no cover
                    pass

    async def _leadership_renew_loop(self) -> None:
        while self._running and self._is_leader:
            await asyncio.sleep(LEADER_RENEW_SECONDS)
            if not await self._renew_leadership():
                logger.info("market_data.manager.leadership_lost")
                return

    # -- local fan-out (same-worker WS clients) -----------------------
    def subscribe_local(self) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=1000)
        self._local_subscribers.add(queue)
        return queue

    def unsubscribe_local(self, queue: asyncio.Queue) -> None:
        self._local_subscribers.discard(queue)

    def _publish_local(self, message: dict) -> None:
        for queue in list(self._local_subscribers):
            try:
                queue.put_nowait(message)
            except asyncio.QueueFull:  # slow client; drop oldest-style
                pass

    async def _emit(self, message: dict) -> None:
        """Publish to Redis pub/sub (cross-worker) and local queues."""
        await store.publish_update(message)
        self._publish_local(message)

    def local_snapshot(self) -> list[dict]:
        return [tick.to_public_dict() for tick in self._ticks.values()]

    def meta_snapshot(self) -> dict:
        return {
            "provider": self._provider_name,
            "connected": self._connected,
            "market_status": self._status.value,
            "stale": self._stale,
            "demo": self.demo_mode,
            "last_tick_at": self._last_tick_at.isoformat() if self._last_tick_at else None,
        }

    # -- tick handling ------------------------------------------------
    async def _on_tick(self, tick: Tick) -> None:
        prev = self._ticks.get(tick.symbol)
        merged = prev.merged_with(tick) if prev else tick
        merged.market_status = self._status
        merged.is_stale = False
        self._ticks[tick.symbol] = merged
        self._last_update_monotonic = monotonic()
        self._last_tick_at = datetime.now(timezone.utc)
        if self._stale:
            self._stale = False
            logger.info("market_data.feed.restored provider=%s", self._provider_name)

        payload = merged.to_public_dict()
        logger.debug(
            "market_data.tick.received symbol=%s ltp=%s", tick.symbol, payload.get("ltp")
        )
        ttl = settings.market_data_cache_ttl_seconds
        await store.save_tick(merged.symbol, payload, ttl)
        await self._emit(
            {
                "type": "ticker_update",
                "provider": self._provider_name,
                "market_status": self._status.value,
                "server_time": datetime.now(timezone.utc).isoformat(),
                "demo": self.demo_mode,
                "data": [payload],
            }
        )

    async def _status_and_stale_loop(self) -> None:
        prev_status = self._status
        while self._running and self._is_leader:
            self._status = compute_market_status()
            if self._status != prev_status:
                prev_status = self._status
                await self._publish_market_status()

            threshold = settings.market_data_stale_seconds
            if should_mark_stale(
                self._status, self._last_update_monotonic, monotonic(), threshold
            ):
                if not self._stale:
                    self._stale = True
                    logger.warning(
                        "market_data.feed.stale provider=%s threshold=%ss",
                        self._provider_name,
                        threshold,
                    )
                    await self._mark_all_stale()
            await self._write_meta()
            await asyncio.sleep(1)

    async def _mark_all_stale(self) -> None:
        ttl = settings.market_data_cache_ttl_seconds
        data = []
        for symbol, tick in self._ticks.items():
            tick.is_stale = True
            payload = tick.to_public_dict()
            data.append(payload)
            await store.save_tick(symbol, payload, ttl)
        if data:
            await self._emit(
                {
                    "type": "ticker_update",
                    "provider": self._provider_name,
                    "market_status": self._status.value,
                    "server_time": datetime.now(timezone.utc).isoformat(),
                    "demo": self.demo_mode,
                    "data": data,
                }
            )

    async def _publish_market_status(self) -> None:
        await self._emit(
            {
                "type": "market_status",
                "market_status": self._status.value,
                "label": status_label(self._status),
                "server_time": datetime.now(timezone.utc).isoformat(),
            }
        )

    async def _publish_provider_status(self) -> None:
        await self._emit(
            {
                "type": "provider_status",
                "provider": self._provider_name,
                "connected": self._connected,
                "demo": self.demo_mode,
                "server_time": datetime.now(timezone.utc).isoformat(),
            }
        )

    async def _write_meta(self) -> None:
        await store.save_meta(
            {
                "provider": self._provider_name,
                "connected": self._connected,
                "market_status": self._status.value,
                "stale": self._stale,
                "demo": self.demo_mode,
                "last_tick_at": self._last_tick_at.isoformat()
                if self._last_tick_at
                else None,
            },
            ttl_seconds=max(settings.market_data_stale_seconds * 3, 30),
        )

    # -- health -------------------------------------------------------
    async def health(self) -> dict:
        redis_ok = await store.redis_healthy()
        status = (
            "healthy"
            if (self._connected or self.demo_mode) and not self._stale
            else "degraded"
        )
        return {
            "status": status,
            "provider": self._provider_name,
            "connected": self._connected,
            "leader": self._is_leader,
            "demo": self.demo_mode,
            "market_status": self._status.value,
            "last_tick_at": self._last_tick_at.isoformat() if self._last_tick_at else None,
            "symbols_subscribed": len(get_index_universe()),
            "redis": "healthy" if redis_ok else "unavailable",
            "stale": self._stale,
        }

    def current_market_status(self) -> MarketStatus:
        return self._status


market_manager = MarketDataManager()
