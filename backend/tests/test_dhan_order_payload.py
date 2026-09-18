import asyncio

from app.brokers.base import OrderRequest
from app.brokers.dhan import DhanAdapter


def _payload(**overrides) -> dict:
    data = dict(
        symbol="RELIANCE",
        exchange="NSE",
        side="BUY",
        quantity=1,
        order_type="MARKET",
        product_type="INTRADAY",
        security_id="2885",
        exchange_segment="NSE_EQ",
    )
    data.update(overrides)
    return DhanAdapter.order_payload(OrderRequest(**data))


def test_dhan_payload_uses_numeric_security_id_and_nse_eq():
    payload = _payload()
    assert payload["securityId"] == "2885"
    assert payload["exchangeSegment"] == "NSE_EQ"
    assert payload["productType"] == "INTRADAY"
    assert payload["transactionType"] == "BUY"


def test_dhan_payload_maps_legacy_intra_alias_to_intraday():
    assert _payload(product_type="INTRA")["productType"] == "INTRADAY"


def test_dhan_payload_maps_delivery_alias_to_cnc():
    assert _payload(product_type="DELIVERY")["productType"] == "CNC"
    assert _payload(product_type="CNC")["productType"] == "CNC"


def test_dhan_intraday_candles_use_intraday_endpoint_and_interval():
    adapter = DhanAdapter(access_token="t", client_id="c")
    captured = {}

    async def fake_request(method, path, **kwargs):
        captured["method"] = method
        captured["path"] = path
        captured["payload"] = kwargs["json"]
        return {
            "open": [100.0, 101.0],
            "high": [101.0, 102.0],
            "low": [99.0, 100.0],
            "close": [101.0, 101.5],
            "volume": [10, 12],
            "timestamp": [1710000000, 1710000300],
        }

    adapter._request = fake_request  # type: ignore[method-assign]
    candles = asyncio.run(
        adapter.get_historical_candles("2885", "NSE", "EQUITY", "5m")
    )
    assert captured["method"] == "POST"
    assert captured["path"] == "/charts/intraday"
    assert captured["payload"]["interval"] == "5"
    assert captured["payload"]["securityId"] == "2885"
    assert " " in captured["payload"]["fromDate"]
    assert len(candles) == 2
    assert candles[0]["close"] == 101.0


def test_dhan_payload_maps_trigger_on_market_to_stop_loss_market():
    payload = _payload(trigger_price=2500.5)
    assert payload["orderType"] == "STOP_LOSS_MARKET"
    assert payload["triggerPrice"] == 2500.5
    assert payload["productType"] == "INTRADAY"
    assert payload["price"] == 0


def test_dhan_payload_maps_trigger_on_limit_to_stop_loss():
    payload = _payload(order_type="LIMIT", price=2499.0, trigger_price=2500.0)
    assert payload["orderType"] == "STOP_LOSS"
    assert payload["triggerPrice"] == 2500.0
    assert payload["price"] == 2499.0


def test_dhan_cover_order_keeps_market_type_and_attaches_trigger():
    payload = _payload(product_type="CO", trigger_price=1418.0)
    assert payload["productType"] == "CO"
    assert payload["orderType"] == "MARKET"
    assert payload["triggerPrice"] == 1418.0


def test_dhan_daily_candles_keep_historical_endpoint():
    adapter = DhanAdapter(access_token="t", client_id="c")
    captured = {}

    async def fake_request(method, path, **kwargs):
        captured["path"] = path
        captured["payload"] = kwargs["json"]
        return {"open": [], "high": [], "low": [], "close": [], "volume": [], "timestamp": []}

    adapter._request = fake_request  # type: ignore[method-assign]
    asyncio.run(adapter.get_historical_candles("13", "NSE", "INDEX", "1D"))
    assert captured["path"] == "/charts/historical"
    assert "interval" not in captured["payload"]
    assert captured["payload"]["instrument"] == "INDEX"
