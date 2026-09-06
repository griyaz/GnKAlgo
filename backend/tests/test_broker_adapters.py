import asyncio
import json

from app.brokers.base import OrderRequest
from app.brokers.factory import get_broker_adapter
from app.brokers.fyers import FyersExecutionAdapter
from app.brokers.upstox import UpstoxExecutionAdapter
from app.core.security import encrypt_data
from app.models import BrokerConnection, BrokerType


def _order(**overrides) -> OrderRequest:
    data = dict(
        symbol="NSE:SBIN-EQ",
        exchange="NSE",
        side="BUY",
        quantity=1,
        order_type="MARKET",
        product_type="INTRADAY",
        security_id="NSE:SBIN-EQ",
    )
    data.update(overrides)
    return OrderRequest(**data)


# --- FYERS payload normalization -------------------------------------------
def test_fyers_payload_market_buy_intraday():
    p = FyersExecutionAdapter.order_payload(_order())
    assert p["type"] == 2 and p["side"] == 1
    assert p["productType"] == "INTRADAY"
    assert p["symbol"] == "NSE:SBIN-EQ"


def test_fyers_payload_limit_sell_cnc():
    p = FyersExecutionAdapter.order_payload(
        _order(side="SELL", order_type="LIMIT", product_type="DELIVERY", price=101.5)
    )
    assert p["type"] == 1 and p["side"] == -1
    assert p["productType"] == "CNC"
    assert p["limitPrice"] == 101.5


# --- Upstox payload normalization ------------------------------------------
def test_upstox_payload_intraday_buy():
    p = UpstoxExecutionAdapter.order_payload(_order(security_id="NSE_EQ|INE123"))
    assert p["product"] == "I"
    assert p["transaction_type"] == "BUY"
    assert p["instrument_token"] == "NSE_EQ|INE123"


def test_upstox_payload_delivery_maps_to_D():
    p = UpstoxExecutionAdapter.order_payload(_order(product_type="CNC"))
    assert p["product"] == "D"


# --- Factory wiring ---------------------------------------------------------
def _conn(broker: BrokerType, creds: dict) -> BrokerConnection:
    return BrokerConnection(
        broker=broker,
        encrypted_credentials=encrypt_data(json.dumps(creds)),
        client_id=creds.get("client_id"),
    )


def test_factory_returns_fyers_adapter():
    adapter = get_broker_adapter(
        _conn(BrokerType.FYERS, {"access_token": "tok", "client_id": "APP-100"})
    )
    assert isinstance(adapter, FyersExecutionAdapter)
    assert adapter.client_id == "APP-100"
    assert "APP-100:tok" == adapter._headers()["Authorization"]


def test_factory_returns_upstox_adapter():
    adapter = get_broker_adapter(_conn(BrokerType.UPSTOX, {"access_token": "tok"}))
    assert isinstance(adapter, UpstoxExecutionAdapter)
    assert adapter._headers()["Authorization"] == "Bearer tok"


# --- Order placement parsing (mocked transport, no real tokens) -------------
def test_fyers_place_order_parses_id(monkeypatch):
    adapter = FyersExecutionAdapter(access_token="t", client_id="APP-100")

    async def fake_request(method, path, **kwargs):
        assert method == "POST" and path == "/orders/sync"
        return {"s": "ok", "id": "808058117761", "message": "Order submitted"}

    monkeypatch.setattr(adapter, "_request", fake_request)
    resp = asyncio.run(adapter.place_order(_order()))
    assert resp.order_id == "808058117761"
    assert resp.broker_order_id == "808058117761"


def test_upstox_place_order_parses_id(monkeypatch):
    adapter = UpstoxExecutionAdapter(access_token="t")

    async def fake_request(method, path, **kwargs):
        assert method == "POST" and path == "/order/place"
        return {"status": "success", "data": {"order_id": "240101010000001"}}

    monkeypatch.setattr(adapter, "_request", fake_request)
    resp = asyncio.run(adapter.place_order(_order(security_id="NSE_EQ|INE123")))
    assert resp.order_id == "240101010000001"


def test_fyers_authenticate_checks_funds(monkeypatch):
    adapter = FyersExecutionAdapter(access_token="", client_id="")
    called = {}

    async def fake_request(method, path, **kwargs):
        called["path"] = path
        return {"s": "ok", "fund_limit": []}

    monkeypatch.setattr(adapter, "_request", fake_request)
    ok = asyncio.run(adapter.authenticate({"access_token": "tok", "client_id": "APP-100"}))
    assert ok is True
    assert adapter.access_token == "tok" and adapter.client_id == "APP-100"
    assert called["path"] == "/funds"
