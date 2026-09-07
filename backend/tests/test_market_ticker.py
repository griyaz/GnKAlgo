"""Tests for the LiveMarketTicker pipeline (Phase 20).

All provider connections are mocked; no real broker tokens are ever required.
"""

import asyncio
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.market_data.manager import MarketDataManager, should_mark_stale
from app.market_data.market_status import compute_market_status
from app.market_data.models import MarketStatus, Tick, compute_change
from app.market_data.providers.base import BackoffPolicy
from app.market_data.providers.dhan import DhanProvider
from app.market_data.providers.fyers import FyersProvider
from app.market_data.providers.mock import MockProvider
from app.market_data.providers.upstox import UpstoxProvider
from app.market_data.symbols import by_fyers_symbol, get_index_universe


# 1. Tick normalization (FYERS + Dhan -> Tick) --------------------------------
def test_fyers_normalization():
    provider = FyersProvider(client_id="APP-100", access_token="tok")
    sym = by_fyers_symbol("NSE:NIFTY50-INDEX")
    assert sym is not None
    msg = {
        "symbol": "NSE:NIFTY50-INDEX",
        "ltp": 25123.5,
        "prev_close_price": 24990.3,
        "open_price": 25020.1,
        "high_price": 25170.0,
        "low_price": 24980.1,
        "exch_feed_time": 1725446400,
    }
    tick = provider.normalize(msg)
    assert tick is not None
    assert tick.symbol == "NIFTY50"
    assert tick.display_name == "NIFTY 50"
    assert tick.provider == "FYERS"
    assert tick.ltp == Decimal("25123.5")
    assert tick.previous_close == Decimal("24990.3")


def test_fyers_normalization_unknown_symbol_ignored():
    provider = FyersProvider(client_id="APP-100", access_token="tok")
    assert provider.normalize({"symbol": "NSE:UNKNOWN-INDEX", "ltp": 1}) is None
    assert provider.normalize({"no_symbol": True}) is None


def test_dhan_normalization():
    provider = DhanProvider(client_id="c", access_token="t")
    sym = get_index_universe()[0]  # NIFTY50 -> IDX_I:13 by default
    packet = {
        "response_code": 2,  # TICKER_PACKET
        "exchange_segment": sym.dhan_segment,
        "security_id": sym.dhan_security_id,
        "ltp": 25100.0,
    }
    tick = provider.normalize(packet)
    assert tick is not None
    assert tick.symbol == sym.id
    assert tick.provider == "DHAN"
    assert tick.ltp == Decimal("25100.0")


def test_upstox_normalization():
    provider = UpstoxProvider(access_token="token")
    sym = get_index_universe()[0]
    ticks = provider.normalize({
        "feeds": {
            sym.upstox: {"ltpc": {"ltp": 25110.0, "cp": 24990.0}},
        },
    })
    assert len(ticks) == 1
    assert ticks[0].symbol == "NIFTY50"
    assert ticks[0].provider == "UPSTOX"
    assert ticks[0].ltp == Decimal("25110.0")


def test_failover_prefers_upstox_before_optional_dhan(monkeypatch):
    monkeypatch.setattr(settings, "market_data_provider", "fyers")
    monkeypatch.setattr(settings, "market_data_failover_enabled", True)
    monkeypatch.setattr(settings, "upstox_market_data_enabled", True)
    monkeypatch.setattr(settings, "dhan_market_data_enabled", True)
    manager = MarketDataManager()
    assert manager._provider_candidates() == ["fyers", "upstox", "dhan"]


# 2 + 3. Percentage calculation + zero previous-close -------------------------
def test_change_percent_calculation():
    change, pct = compute_change(Decimal("25123.50"), Decimal("24990.30"))
    assert change == Decimal("133.20")
    assert round(float(pct), 2) == 0.53


def test_zero_previous_close_is_safe():
    change, pct = compute_change(Decimal("101"), Decimal("0"))
    assert change == Decimal("101")
    assert pct == Decimal("0")  # no ZeroDivisionError


def test_missing_values_change_none():
    assert compute_change(None, Decimal("100")) == (None, None)
    assert compute_change(Decimal("100"), None) == (None, None)


# 8. Redis serialization round-trip ------------------------------------------
def test_tick_redis_round_trip():
    tick = Tick(
        symbol="NIFTY50",
        display_name="NIFTY 50",
        exchange="NSE",
        provider="FYERS",
        ltp=Decimal("25123.50"),
        previous_close=Decimal("24990.30"),
        market_status=MarketStatus.OPEN,
    )
    payload = tick.to_public_dict()
    assert payload["ltp"] == 25123.5
    assert payload["change"] == 133.2
    assert payload["change_percent"] == 0.53
    assert payload["market_status"] == "OPEN"
    restored = Tick.from_public_dict(payload)
    assert restored.symbol == "NIFTY50"
    assert restored.ltp == Decimal("25123.5")
    assert restored.market_status == MarketStatus.OPEN


def test_tick_merge_retains_prev_close():
    base = Tick("NIFTY50", "NIFTY 50", "NSE", "DHAN", previous_close=Decimal("100"))
    ltp_only = Tick("NIFTY50", "NIFTY 50", "NSE", "DHAN", ltp=Decimal("105"))
    merged = base.merged_with(ltp_only)
    assert merged.ltp == Decimal("105")
    assert merged.previous_close == Decimal("100")
    assert merged.change == Decimal("5")


# 5. Reconnect logic (backoff schedule + reset) ------------------------------
def test_backoff_schedule_and_reset():
    policy = BackoffPolicy()
    delays = [policy.next_delay() for _ in range(7)]
    # Each delay is within [0.5*step, step] for the 1,2,4,8,15,30,30 schedule.
    caps = [1, 2, 4, 8, 15, 30, 30]
    for delay, cap in zip(delays, caps):
        assert cap * 0.5 - 0.001 <= delay <= cap + 0.001
    policy.reset()
    first = policy.next_delay()
    assert 0.5 - 0.001 <= first <= 1.0 + 0.001


# 6. Stale tick detection ----------------------------------------------------
def test_should_mark_stale():
    now = 1000.0
    assert should_mark_stale(MarketStatus.OPEN, now - 20, now, 10) is True
    assert should_mark_stale(MarketStatus.OPEN, now - 5, now, 10) is False
    # Closed market never stale, even with old data.
    assert should_mark_stale(MarketStatus.CLOSED, now - 999, now, 10) is False
    assert should_mark_stale(MarketStatus.OPEN, None, now, 10) is False


# 7. Market closed behavior --------------------------------------------------
def test_market_status_weekend_and_holiday():
    saturday = datetime(2026, 9, 5, 11, 0, tzinfo=timezone.utc)  # Sat
    assert compute_market_status(saturday) == MarketStatus.CLOSED

    # A weekday within session hours (IST) is OPEN, unless configured holiday.
    weekday_open = datetime(2026, 9, 7, 5, 0, tzinfo=timezone.utc)  # Mon 10:30 IST
    assert compute_market_status(weekday_open) == MarketStatus.OPEN

    original = settings.market_holidays
    settings.market_holidays = "2026-09-07"
    try:
        assert compute_market_status(weekday_open) == MarketStatus.HOLIDAY
    finally:
        settings.market_holidays = original


# 4. Provider disconnection --------------------------------------------------
def test_mock_provider_stream_ends_on_disconnect():
    async def scenario():
        provider = MockProvider(interval_seconds=0.01)
        await provider.connect()
        await provider.subscribe(list(get_index_universe()))

        received: list = []

        async def consume():
            async for tick in provider.stream():
                received.append(tick)

        task = asyncio.create_task(consume())
        await asyncio.sleep(0.05)
        await provider.disconnect()
        await asyncio.wait_for(task, timeout=1.0)
        return received

    received = asyncio.run(scenario())
    assert len(received) > 0  # produced ticks, then stopped cleanly


# Manager end-to-end in mock mode (normalize -> local fan-out) ---------------
def test_manager_mock_publishes_ticker_updates(monkeypatch):
    monkeypatch.setattr(settings, "market_data_mock_mode", True)

    async def scenario():
        manager = MarketDataManager()
        queue = manager.subscribe_local()
        manager.start()
        types = set()
        sample = None
        try:
            for _ in range(10):
                msg = await asyncio.wait_for(queue.get(), timeout=5)
                types.add(msg["type"])
                if msg["type"] == "ticker_update":
                    sample = msg
        finally:
            await manager.stop()
        health = await manager.health()
        return types, sample, health

    types, sample, health = asyncio.run(scenario())
    assert "ticker_update" in types
    assert sample is not None
    assert sample["provider"] == "MOCK"
    assert sample["demo"] is True
    item = sample["data"][0]
    assert "ltp" in item and "change_percent" in item
    assert "access_token" not in item  # never leak credentials
    assert health["provider"] == "MOCK"
    assert health["symbols_subscribed"] == len(get_index_universe())


# 9. WebSocket snapshot ------------------------------------------------------
def test_ws_ticker_snapshot(monkeypatch):
    from app.market_data.manager import market_manager

    monkeypatch.setattr(settings, "market_data_require_auth", False)
    # Seed one in-process tick so the snapshot has data without Redis.
    market_manager._ticks.clear()
    market_manager._ticks["NIFTY50"] = Tick(
        symbol="NIFTY50",
        display_name="NIFTY 50",
        exchange="NSE",
        provider="MOCK",
        ltp=Decimal("25123.50"),
        previous_close=Decimal("24990.30"),
        market_status=MarketStatus.OPEN,
    )
    try:
        with TestClient(app) as client:
            with client.websocket_connect("/ws/market/ticker") as ws:
                snap = ws.receive_json()
                assert snap["type"] == "snapshot"
                assert isinstance(snap["data"], list)
                symbols = {d["symbol"] for d in snap["data"]}
                assert "NIFTY50" in symbols
                nifty = next(d for d in snap["data"] if d["symbol"] == "NIFTY50")
                assert nifty["ltp"] == 25123.5
                assert nifty["change"] == 133.2
    finally:
        market_manager._ticks.clear()


def test_ws_ticker_requires_auth_by_default(monkeypatch):
    monkeypatch.setattr(settings, "market_data_require_auth", True)
    with TestClient(app) as client:
        with pytest.raises(Exception):
            with client.websocket_connect("/ws/market/ticker") as ws:
                # Auth message without a token -> server rejects, no snapshot.
                ws.send_json({"action": "auth"})
                ws.receive_json()


def test_rest_ticker_snapshot_endpoint():
    with TestClient(app) as client:
        res = client.get("/api/v1/market/ticker")
        assert res.status_code == 200
        body = res.json()
        assert body["type"] == "snapshot"
        assert isinstance(body["data"], list)


def test_rest_market_health_endpoint():
    with TestClient(app) as client:
        res = client.get("/api/v1/market/health")
        assert res.status_code == 200
        body = res.json()
        assert "provider" in body
        assert "symbols_subscribed" in body
        assert body["symbols_subscribed"] == len(get_index_universe())
