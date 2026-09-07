import json
from datetime import datetime

from app.config import settings
from app.core.security import encrypt_data
from app.models import BrokerConnection, BrokerType
from app.services.live_trading import _credential_errors
from app.services.risk import RiskRejection, validate_order


def test_live_orders_reject_configured_market_holiday(monkeypatch):
    monkeypatch.setattr(settings, "market_holidays", "2026-08-24")
    with __import__("pytest").raises(RiskRejection, match="market hours"):
        validate_order(
            quantity=1,
            paper_mode=False,
            now=datetime(2026, 8, 24, 10, 0),
        )


def test_dhan_live_gate_requires_valid_static_ip(monkeypatch):
    monkeypatch.setattr(settings, "dhan_static_ip", "not-an-ip")
    connection = BrokerConnection(
        broker=BrokerType.DHAN,
        encrypted_credentials=encrypt_data(json.dumps({"access_token": "token", "client_id": "client"})),
        client_id="client",
    )
    assert "Dhan static public IP is invalid" in _credential_errors(BrokerType.DHAN, connection)


def test_fyers_live_gate_requires_client_id():
    connection = BrokerConnection(
        broker=BrokerType.FYERS,
        encrypted_credentials=encrypt_data(json.dumps({"access_token": "token"})),
    )
    assert "FYERS client ID is required" in _credential_errors(BrokerType.FYERS, connection)
