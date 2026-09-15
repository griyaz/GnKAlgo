"""FYERS API v3 OAuth helpers.

FYERS v3 uses ``generate-authcode`` followed by ``validate-authcode``.
The token request contains ``appIdHash = SHA256(client_id + ':' + secret_key)``.
Secrets and upstream response bodies are intentionally never included in errors.
"""

import hashlib
import json
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import httpx

from app.config import settings
from app.core.security import decrypt_data, encrypt_data


class FyersOAuthError(RuntimeError):
    """A safe, user-facing OAuth failure without upstream credentials."""


class FyersOAuth2:
    AUTH_URL = "https://api-t1.fyers.in/api/v3/generate-authcode"
    TOKEN_URL = "https://api-t1.fyers.in/api/v3/validate-authcode"

    def __init__(self, client_id: str | None = None, client_secret: str | None = None, redirect_uri: str | None = None):
        self.client_id = client_id or settings.fyers_client_id
        self.client_secret = client_secret or settings.fyers_secret_key
        self.redirect_uri = redirect_uri or settings.fyers_redirect_url

    def get_auth_url(self, state: str) -> str:
        if not self.client_id or not self.redirect_uri:
            raise FyersOAuthError("FYERS OAuth is not configured")
        return f"{self.AUTH_URL}?{urlencode({'client_id': self.client_id, 'redirect_uri': self.redirect_uri, 'response_type': 'code', 'state': state})}"

    def app_id_hash(self) -> str:
        if not self.client_id or not self.client_secret:
            raise FyersOAuthError("FYERS OAuth is not configured")
        return hashlib.sha256(f"{self.client_id}:{self.client_secret}".encode()).hexdigest()

    async def exchange_code_for_token(self, auth_code: str) -> dict:
        payload = {"grant_type": "authorization_code", "appIdHash": self.app_id_hash(), "code": auth_code}
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(15.0, connect=5.0)) as client:
                response = await client.post(self.TOKEN_URL, json=payload)
        except httpx.HTTPError as exc:
            raise FyersOAuthError("FYERS authorization service is unavailable") from exc
        if response.status_code != 200:
            raise FyersOAuthError("FYERS authorization was rejected")
        try:
            data = response.json()
        except ValueError as exc:
            raise FyersOAuthError("FYERS returned an invalid authorization response") from exc
        if not isinstance(data, dict) or data.get("s") == "error" or not data.get("access_token"):
            raise FyersOAuthError("FYERS authorization was rejected")
        return {
            "access_token": str(data["access_token"]),
            "expires_in": int(data.get("expires_in", 86400)),
            "token_type": str(data.get("token_type", "Bearer")),
            "client_id": self.client_id,
        }


class FyersTokenStore:
    @staticmethod
    def store_tokens(access_token: str, expires_in: int, client_id: str) -> str:
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=max(1, expires_in))
        return encrypt_data(json.dumps({
            "access_token": access_token,
            "expires_at": expires_at.isoformat(),
            "token_type": "Bearer",
            "client_id": client_id,
        }))

    @staticmethod
    def load_tokens(encrypted: str) -> dict:
        return json.loads(decrypt_data(encrypted))
