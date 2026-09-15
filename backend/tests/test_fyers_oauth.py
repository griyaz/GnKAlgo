import uuid
import hashlib
from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient

from app.brokers.fyers_oauth import FyersOAuth2, FyersOAuthError
from app.config import settings
from app.main import app

settings.fyers_client_id = "TESTAPP-100"
settings.fyers_secret_key = "test-secret"
settings.fyers_redirect_url = "https://gnkalgo.com/fyers/callback"


def _login(client: TestClient) -> dict:
    email = f"fyers-{uuid.uuid4().hex[:10]}@gnkalgo.com"
    password = "SecurePass1!"
    registered = client.post("/api/v1/auth/register", json={
        "email": email, "password": password, "full_name": "FYERS Tester",
        "phone": f"98{uuid.uuid4().int % 10**8:08d}",
    })
    assert registered.status_code == 201
    verify_token = registered.json()["message"].split("token=")[-1]
    assert client.post("/api/v1/auth/verify-email", json={"token": verify_token}).status_code == 200
    login = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert login.status_code == 200
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def test_fyers_login_url_requires_auth_and_has_v3_parameters():
    with TestClient(app) as client:
        assert client.get("/api/v1/brokers/fyers/login").status_code == 401
        headers = _login(client)
        response = client.get("/api/v1/brokers/fyers/login", headers=headers)
        assert response.status_code == 200
        parsed = urlparse(response.json()["authorization_url"])
        params = parse_qs(parsed.query)
        assert parsed.path.endswith("/generate-authcode")
        assert params["redirect_uri"] == ["https://gnkalgo.com/fyers/callback"]
        assert params["response_type"] == ["code"]
        assert "state" in params


def test_fyers_callback_is_one_time_and_stores_no_plain_token(monkeypatch):
    secret_token = "fyers-secret-access-token"

    async def exchange(self, auth_code):
        return {"access_token": secret_token, "expires_in": 900, "client_id": self.client_id}

    monkeypatch.setattr(FyersOAuth2, "exchange_code_for_token", exchange)
    with TestClient(app) as client:
        headers = _login(client)
        login = client.get("/api/v1/brokers/fyers/login", headers=headers).json()
        state = parse_qs(urlparse(login["authorization_url"]).query)["state"][0]
        callback = client.post(
            "/api/v1/brokers/fyers/callback", headers=headers,
            json={"auth_code": "one-time-code", "state": state},
        )
        assert callback.status_code == 200
        assert secret_token not in callback.text
        assert client.get("/api/v1/brokers/fyers/status", headers=headers).json()["status"] == "connected"
        replay = client.post(
            "/api/v1/brokers/fyers/callback", headers=headers,
            json={"auth_code": "one-time-code", "state": state},
        )
        assert replay.status_code == 400


def test_fyers_callback_exchange_failure_is_redacted(monkeypatch):
    secret = "upstream-secret-body"

    async def exchange(self, auth_code):
        raise FyersOAuthError(f"rejected: {secret}")

    monkeypatch.setattr(FyersOAuth2, "exchange_code_for_token", exchange)
    with TestClient(app) as client:
        headers = _login(client)
        login = client.get("/api/v1/brokers/fyers/login", headers=headers).json()
        state = parse_qs(urlparse(login["authorization_url"]).query)["state"][0]
        response = client.post(
            "/api/v1/brokers/fyers/callback", headers=headers,
            json={"auth_code": "bad-code", "state": state},
        )
        assert response.status_code == 502
        assert secret not in response.text


def test_fyers_app_id_hash_uses_documented_v3_input():
    oauth = FyersOAuth2("APP-100", "secret", "https://gnkalgo.com/fyers/callback")
    assert oauth.app_id_hash() == hashlib.sha256(b"APP-100:secret").hexdigest()
