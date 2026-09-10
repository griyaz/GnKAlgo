import os
import uuid

os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./test_gnkalgo.db"

from fastapi.testclient import TestClient

from app.config import settings
from app.main import app


def test_health():
    with TestClient(app) as client:
        res = client.get("/health")
        assert res.status_code == 200
        assert res.json()["status"] == "ok"


def test_api_root():
    with TestClient(app) as client:
        res = client.get("/api/v1/")
        assert res.status_code == 200
        body = res.json()
        assert body["service"] == "gnkalgo-backend"
        assert "endpoints" in body


def test_core_application_routers_are_mounted():
    """Prevent replacing app.main with a stub that drops the trading API."""
    paths = {getattr(route, "path", "") for route in app.routes}
    required = (
        "/health",
        "/health/ready",
        "/api/v1/auth/login",
        "/api/v1/auth/register",
        "/api/v1/orders/",
        "/api/v1/strategies/",
        "/api/v1/billing/plans",
        "/api/v1/market/indices",
        "/api/v1/profile/",
        "/api/v1/portfolio/holdings",
        "/api/v1/alerts/",
        "/api/v1/webhooks/",
        "/ws/market/ticker",
    )
    missing = [path for path in required if path not in paths]
    assert not missing, f"core routes missing from app.main: {missing}"


def test_register_verify_login():
    with TestClient(app) as client:
        email = f"devtrader-{uuid.uuid4().hex[:8]}@gnkalgo.com"
        password = "SecurePass1!"
        res = client.post(
            "/api/v1/auth/register",
            json={
                "email": email,
                "password": password,
                "full_name": "Dev Trader",
                "phone": f"98{uuid.uuid4().int % 10**8:08d}",
            },
        )
        assert res.status_code == 201
        message = res.json()["message"]
        assert "token=" in message
        token = message.split("token=")[-1]
        verify = client.post("/api/v1/auth/verify-email", json={"token": token})
        assert verify.status_code == 200
        login = client.post("/api/v1/auth/login", json={"email": email, "password": password})
        assert login.status_code == 200
        access = login.json()["access_token"]
        me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {access}"})
        assert me.status_code == 200
        assert me.json()["email"] == email
        paper = client.post(
            "/api/v1/orders/",
            headers={"Authorization": f"Bearer {access}"},
            json={"symbol": "RELIANCE", "side": "BUY", "quantity": 1, "paper_mode": True, "broker": "paper"},
        )
        assert paper.status_code == 200
        assert paper.json()["status"] == "PAPER_FILLED"
        live = client.post(
            "/api/v1/orders/",
            headers={"Authorization": f"Bearer {access}"},
            json={"symbol": "RELIANCE", "side": "BUY", "quantity": 1, "paper_mode": False, "broker": "dhan"},
        )
        assert live.status_code == 200
        assert live.json()["status"] == "REJECTED"
        msg = live.json()["message"].lower()
        assert "subscription" in msg or "market hours" in msg


def test_login_allows_unverified_users_when_smtp_is_unconfigured():
    original_host = settings.smtp_host
    original_from = settings.smtp_from
    settings.smtp_host = ""
    settings.smtp_from = ""
    try:
        with TestClient(app) as client:
            email = f"localdev-{uuid.uuid4().hex[:8]}@gnkalgo.com"
            password = "SecurePass1!"
            register = client.post(
                "/api/v1/auth/register",
                json={
                    "email": email,
                    "password": password,
                    "full_name": "Local Dev User",
                    "phone": f"96{uuid.uuid4().int % 10**8:08d}",
                },
            )
            assert register.status_code == 201
            login = client.post("/api/v1/auth/login", json={"email": email, "password": password})
            assert login.status_code == 200
            assert login.json()["access_token"]
    finally:
        settings.smtp_host = original_host
        settings.smtp_from = original_from


def test_example_smtp_placeholders_do_not_block_development_login():
    original = (
        settings.app_env,
        settings.smtp_host,
        settings.smtp_user,
        settings.smtp_password,
        settings.smtp_from,
    )
    settings.app_env = "development"
    settings.smtp_host = "mail.privateemail.com"
    settings.smtp_user = "noreply@gnkalgo.com"
    settings.smtp_password = "replace-with-mailbox-password"
    settings.smtp_from = "noreply@gnkalgo.com"
    try:
        with TestClient(app) as client:
            email = f"placeholder-{uuid.uuid4().hex[:8]}@example.com"
            password = "StrongPass123!"
            registered = client.post(
                "/api/v1/auth/register",
                json={"email": email, "password": password, "full_name": "Placeholder SMTP"},
            )
            assert registered.status_code == 201, registered.text
            assert "SMTP is not configured" in registered.json()["message"]

            login = client.post(
                "/api/v1/auth/login",
                json={"email": email, "password": password},
            )
            assert login.status_code == 200, login.text
    finally:
        (
            settings.app_env,
            settings.smtp_host,
            settings.smtp_user,
            settings.smtp_password,
            settings.smtp_from,
        ) = original
def test_failed_logins_persist_and_lock_account():
    with TestClient(app) as client:
        email = f"lockout-{uuid.uuid4().hex[:8]}@gnkalgo.com"
        password = "SecurePass1!"
        register = client.post(
            "/api/v1/auth/register",
            json={
                "email": email,
                "password": password,
                "full_name": "Lockout User",
                "phone": f"97{uuid.uuid4().int % 10**8:08d}",
            },
        )
        assert register.status_code == 201
        token = register.json()["message"].split("token=")[-1]
        assert client.post("/api/v1/auth/verify-email", json={"token": token}).status_code == 200

        for _ in range(5):
            failed = client.post(
                "/api/v1/auth/login",
                json={"email": email, "password": "WrongPass1!"},
            )
            assert failed.status_code == 401
            assert failed.json()["detail"] == "Invalid email or password"

        locked = client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": password},
        )
        assert locked.status_code == 401
        assert locked.json()["detail"] == "Account temporarily locked. Try again later."
