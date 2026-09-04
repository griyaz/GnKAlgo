import hashlib
import hmac
import json
import uuid
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.config import settings
from app.main import app


def _register_login(client: TestClient, email: str, password: str = "Strong!Pass123") -> str:
    registered = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "full_name": "Security User"},
    )
    assert registered.status_code == 201
    logged_in = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert logged_in.status_code == 200
    return logged_in.json()["access_token"]


def test_cookie_auth_csrf_and_registration_profile_fields():
    with TestClient(app) as client:
        email = f"secure-{uuid.uuid4().hex[:8]}@gnkalgo.com"
        password = "Strong!Pass123"
        registered = client.post("/api/v1/auth/register", json={
            "email": email,
            "password": password,
            "full_name": "Security User",
            "gender": "Other",
            "date_of_birth": "1990-12-31",
        })
        assert registered.status_code == 201

        logged_in = client.post("/api/v1/auth/login", json={"email": email, "password": password})
        assert logged_in.status_code == 200
        assert logged_in.cookies.get("gnk_access")
        assert "gnk_access=" in logged_in.headers["set-cookie"]
        assert "HttpOnly" in logged_in.headers["set-cookie"]

        assert client.get("/api/v1/profile/").status_code == 200
        profile = client.get("/api/v1/profile/").json()
        assert profile["gender"] == "Other"
        assert profile["date_of_birth"] == "1990-12-31"

        blocked = client.post("/api/v1/orders/", json={
            "symbol": "RELIANCE", "side": "BUY", "quantity": 1, "paper_mode": True, "broker": "paper"
        })
        assert blocked.status_code == 403
        assert blocked.json()["detail"] == "CSRF validation failed"

        csrf = client.cookies.get("gnk_csrf")
        paper = client.post("/api/v1/orders/", headers={"X-CSRF-Token": csrf}, json={
            "symbol": "RELIANCE", "side": "BUY", "quantity": 1, "paper_mode": True, "broker": "paper"
        })
        assert paper.status_code == 200
        assert paper.json()["status"] == "PAPER_FILLED"


def test_manual_live_orders_require_confirmation_webhooks_do_not():
    """UI live orders need the typed phrase; HMAC webhooks must still be able to trade live."""
    email = f"live-{uuid.uuid4().hex[:8]}@gnkalgo.com"
    admin_email = f"admin-{uuid.uuid4().hex[:8]}@gnkalgo.com"
    original_admin = settings.admin_emails
    original_ip = settings.dhan_static_ip
    settings.admin_emails = admin_email
    settings.dhan_static_ip = "203.0.113.10"
    try:
        with patch("app.services.risk.is_market_hours", return_value=True):
            with TestClient(app) as client:
                access = _register_login(client, email)
                auth = {"Authorization": f"Bearer {access}"}
                admin_access = _register_login(client, admin_email)
                admin_auth = {"Authorization": f"Bearer {admin_access}"}

                switched = client.put(
                    "/api/v1/admin/trading/kill-switch",
                    headers=admin_auth,
                    json={"active": False, "reason": "test"},
                )
                assert switched.status_code == 200
                assert switched.json()["active"] is False

                live = client.post(
                    "/api/v1/orders/",
                    headers=auth,
                    json={
                        "symbol": "RELIANCE",
                        "side": "BUY",
                        "quantity": 1,
                        "paper_mode": False,
                        "broker": "dhan",
                    },
                )
                assert live.status_code == 200
                assert live.json()["status"] == "REJECTED"
                assert "CONFIRM LIVE ORDER" in live.json()["message"]

                confirmed = client.post(
                    "/api/v1/orders/",
                    headers=auth,
                    json={
                        "symbol": "RELIANCE",
                        "side": "BUY",
                        "quantity": 1,
                        "paper_mode": False,
                        "broker": "dhan",
                        "live_confirmation": "CONFIRM LIVE ORDER",
                    },
                )
                assert confirmed.status_code == 200
                assert confirmed.json()["status"] == "REJECTED"
                assert "subscription" in confirmed.json()["message"].lower()
                assert "CONFIRM LIVE ORDER" not in confirmed.json()["message"]

                checkout = client.post("/api/v1/billing/checkout", headers=auth, json={"plan_code": "DAILY"})
                payment_id = checkout.json()["payment_id"]
                client.post(f"/api/v1/billing/payments/{payment_id}/utr", headers=auth, json={"utr": "123456789012"})
                confirm_pay = client.post(
                    f"/api/v1/admin/payments/{payment_id}/confirm",
                    headers=admin_auth,
                )
                assert confirm_pay.status_code == 200

                created = client.post(
                    "/api/v1/webhooks/",
                    headers=auth,
                    json={"name": "TV", "direction": "INBOUND"},
                )
                assert created.status_code == 200
                secret = created.json()["secret"]
                token = created.json()["token"]
                body = json.dumps(
                    {"symbol": "RELIANCE", "action": "BUY", "qty": 1, "paper_mode": False}
                ).encode()
                sig = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
                hooked = client.post(
                    f"/api/v1/webhooks/in/{token}",
                    content=body,
                    headers={
                        "Content-Type": "application/json",
                        "X-Gnkalgo-Secret": secret,
                        "X-Gnkalgo-Signature": sig,
                    },
                )
                assert hooked.status_code == 200, hooked.text
                assert hooked.json()["accepted"] is True
                payload = json.loads(hooked.json()["response"])
                assert payload["status"] == "REJECTED"
                orders = client.get("/api/v1/orders/", headers=auth)
                webhook_order = next(o for o in orders.json() if o["id"] == payload["order_id"])
                assert "CONFIRM LIVE ORDER" not in (webhook_order.get("message") or "")
                assert "mfa" in (webhook_order.get("message") or "").lower()
    finally:
        settings.admin_emails = original_admin
        settings.dhan_static_ip = original_ip
