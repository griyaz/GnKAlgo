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
