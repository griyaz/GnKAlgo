"""Chart WebSocket must not fan live Dhan ticks out to users without a broker."""

import asyncio
import json

from app.brokers.dhan_feed_parser import TICKER_PACKET
from app.services import market_ws_manager as mws


class FakeWS:
    def __init__(self) -> None:
        self.messages: list[dict] = []

    async def send_text(self, payload: str) -> None:
        self.messages.append(json.loads(payload))


class FakeFeed:
    def __init__(self) -> None:
        self.subscribed: list = []

    async def subscribe(self, instruments) -> None:
        self.subscribed.append(instruments)

    async def unsubscribe(self, instruments) -> None:
        return None


def _inst(symbol: str = "RELIANCE", exchange: str = "NSE") -> dict:
    return {
        "symbol": symbol,
        "exchange": exchange,
        "security_id": "2885",
        "dhan_segment": "NSE_EQ",
        "feed_key": "NSE_EQ:2885",
        "segment": "EQUITY",
    }


def _reset() -> None:
    mws._client_subscribers.clear()
    mws._instrument_refcount.clear()
    mws._instrument_meta.clear()
    mws._user_feeds.clear()
    mws._user_creds.clear()


def _patch_production(monkeypatch) -> FakeFeed:
    feed = FakeFeed()

    async def fake_resolve(symbol: str, exchange: str) -> dict:
        return _inst(symbol.upper(), exchange.upper())

    async def fake_ensure(user_id: str, creds: dict) -> FakeFeed:
        mws._user_feeds[user_id] = feed
        mws._user_creds[user_id] = creds
        return feed

    monkeypatch.setattr(mws, "_use_mock", lambda: False)
    monkeypatch.setattr(mws, "_resolve_instrument", fake_resolve)
    monkeypatch.setattr(mws, "_ensure_user_feed", fake_ensure)
    return feed


def test_unentitled_client_does_not_receive_another_users_dhan_ticks(monkeypatch):
    _reset()
    _patch_production(monkeypatch)
    entitled = FakeWS()
    stranger = FakeWS()

    async def scenario():
        await mws.subscribe_ws(entitled, "user-a", "RELIANCE", "NSE", {"access_token": "t", "client_id": "c"})
        await mws.subscribe_ws(stranger, "user-b", "RELIANCE", "NSE", None)
        await mws._on_dhan_tick(
            "user-a",
            {
                "response_code": TICKER_PACKET,
                "exchange_segment": "NSE_EQ",
                "security_id": "2885",
                "ltp": 2850.25,
                "ltt": 1_700_000_000,
                "volume": 10,
            },
        )

    asyncio.run(scenario())

    key = "RELIANCE:NSE"
    assert entitled in mws._client_subscribers.get(key, set())
    assert stranger not in mws._client_subscribers.get(key, set())
    assert any(m.get("code") == "BROKER_REQUIRED" for m in stranger.messages)
    ticks = [m for m in entitled.messages if m.get("type") == "tick"]
    assert ticks and ticks[-1]["ltp"] == 2850.25
    assert ticks[-1]["source"] == "dhan"
    assert not any(m.get("type") == "tick" for m in stranger.messages)
    _reset()


def test_failed_subscribe_does_not_stay_registered_for_later_live_feed(monkeypatch):
    _reset()
    _patch_production(monkeypatch)
    stranger = FakeWS()
    entitled = FakeWS()

    async def scenario():
        await mws.subscribe_ws(stranger, "user-b", "RELIANCE", "NSE", None)
        await mws.subscribe_ws(entitled, "user-a", "RELIANCE", "NSE", {"access_token": "t", "client_id": "c"})
        await mws._broadcast_to_clients(
            "RELIANCE:NSE",
            {"type": "tick", "symbol": "RELIANCE", "ltp": 1.0, "source": "dhan"},
        )

    asyncio.run(scenario())

    assert stranger not in mws._client_subscribers.get("RELIANCE:NSE", set())
    assert not any(m.get("type") == "tick" for m in stranger.messages)
    assert any(m.get("type") == "tick" for m in entitled.messages)
    _reset()
