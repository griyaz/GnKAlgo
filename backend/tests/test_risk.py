from datetime import datetime

import pytest

from app.schemas.auth import RegisterRequest
from app.services.risk import (
    UNKNOWN_SYMBOL_RISK_PRICE,
    RiskRejection,
    is_market_hours,
    notional_price,
    validate_order,
)
from app.services.candle_service import BASE_PRICES
from app.services import market_quote_cache


def test_password_rules_reject_weak():
    with pytest.raises(Exception):
        RegisterRequest(email="a@b.com", password="short", full_name="Test User")


def test_password_rules_accept_strong():
    data = RegisterRequest(
        email="trader@gnkalgo.com",
        password="SecurePass1!",
        full_name="Test Trader",
        phone="9876543210",
    )
    assert data.email == "trader@gnkalgo.com"


def test_paper_order_allowed_off_hours():
    validate_order(quantity=10, paper_mode=True, now=datetime(2026, 8, 23, 22, 0))


def test_live_order_blocked_weekend():
    weekend = datetime(2026, 8, 23, 11, 0)  # Sunday
    with pytest.raises(RiskRejection):
        validate_order(quantity=10, paper_mode=False, now=weekend)


def test_quantity_cap():
    with pytest.raises(RiskRejection):
        validate_order(quantity=9999, max_quantity=500, paper_mode=True)


def test_market_hours_weekday_open():
    open_time = datetime(2026, 8, 24, 10, 0)  # Monday
    assert is_market_hours(open_time) is True


def test_notional_price_keeps_explicit_fill():
    assert notional_price("RELIANCE", 2700.5) == 2700.5


def test_notional_price_market_order_uses_curated_base():
    assert notional_price("RELIANCE", None) == BASE_PRICES["RELIANCE"]
    assert notional_price("RELIANCE", 0) == BASE_PRICES["RELIANCE"]


def test_notional_price_unknown_symbol_is_not_zero():
    assert notional_price("NOTAREALTICKER", None) == UNKNOWN_SYMBOL_RISK_PRICE
    assert notional_price("NOTAREALTICKER", None) > 0


def test_notional_price_prefers_live_quote_cache():
    market_quote_cache.update_ltp("NSE_EQ", "99999", 4321.0, symbol="CACHEONLY")
    try:
        assert notional_price("CACHEONLY", None) == 4321.0
    finally:
        market_quote_cache._store.pop(market_quote_cache.feed_key("NSE_EQ", "99999"), None)
