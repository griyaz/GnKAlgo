"""FYERS OAuth2 authentication flow.

Replaces static token-based auth with OAuth2 for better security:
- Short-lived access tokens (15 min)
- Long-lived refresh tokens (30 days)
- Automatic token refresh
- Revocation support
"""

import httpx
import json
from datetime import datetime, timedelta, timezone
from typing import Optional

from app.config import settings
from app.core.security import encrypt_data, decrypt_data


class FyersOAuth2:
    """Handle FYERS OAuth2 token exchange and refresh."""
    
    OAUTH_BASE = "https://api-t1.fyers.in/oauth2"
    API_BASE = "https://api-t1.fyers.in/api/v3"
    
    def __init__(self, client_id: str, client_secret: str, redirect_uri: str | None = None):
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri or f"{settings.api_base_url}/auth/brokers/fyers/callback"
    
    def get_auth_url(self, state: str) -> str:
        """Generate FYERS OAuth login URL.
        
        User navigates to this URL, logs in, authorizes app → redirected to callback.
        """
        return (
            f"{self.OAUTH_BASE}/authorize?"
            f"client_id={self.client_id}&"
            f"redirect_uri={self.redirect_uri}&"
            f"scope=order,holdings,positions&"
            f"state={state}&"
            f"response_type=code"
        )
    
    async def exchange_code_for_token(self, auth_code: str) -> dict:
        """Exchange authorization code for access + refresh tokens.
        
        Called by callback handler after user authorizes.
        """
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.OAUTH_BASE}/token",
                json={
                    "grant_type": "authorization_code",
                    "code": auth_code,
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "redirect_uri": self.redirect_uri,
                }
            )
            if response.status_code != 200:
                raise RuntimeError(f"OAuth token exchange failed: {response.text}")
            
            data = response.json()
            return {
                "access_token": data["access_token"],
                "refresh_token": data["refresh_token"],
                "expires_in": data.get("expires_in", 900),  # 15 min default
                "token_type": data.get("token_type", "Bearer"),
            }
    
    async def refresh_access_token(self, refresh_token: str) -> dict:
        """Refresh expired access token using refresh token.
        
        Called automatically before token expires.
        """
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.OAUTH_BASE}/token",
                json={
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                }
            )
            if response.status_code != 200:
                raise RuntimeError(f"Token refresh failed: {response.text}")
            
            data = response.json()
            return {
                "access_token": data["access_token"],
                "refresh_token": data.get("refresh_token", refresh_token),  # Might be same
                "expires_in": data.get("expires_in", 900),
            }
    
    async def revoke_token(self, refresh_token: str) -> bool:
        """Revoke refresh token (logout).
        
        Called when user disconnects broker.
        """
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.OAUTH_BASE}/revoke",
                json={
                    "token": refresh_token,
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                }
            )
            return response.status_code == 200


class FyersTokenStore:
    """Store Fyers OAuth tokens in BrokerConnection with refresh logic.
    
    Schema:
    {
        "access_token": "...",
        "refresh_token": "...",
        "expires_at": "2026-09-10T12:30:00Z",  # ISO 8601
        "token_type": "Bearer",
        "client_id": "ABCD1234-100"
    }
    """
    
    @staticmethod
    def store_tokens(access_token: str, refresh_token: str, expires_in: int, 
                     client_id: str) -> str:
        """Serialize and encrypt tokens for storage in DB."""
        expires_at = (datetime.now(timezone.utc) + timedelta(seconds=expires_in)).isoformat()
        data = {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "expires_at": expires_at,
            "token_type": "Bearer",
            "client_id": client_id,
        }
        return encrypt_data(json.dumps(data))
    
    @staticmethod
    def load_tokens(encrypted: str) -> dict:
        """Decrypt and deserialize tokens from DB."""
        return json.loads(decrypt_data(encrypted))
    
    @staticmethod
    def is_token_expired(encrypted: str) -> bool:
        """Check if access token has expired or is close to expiring (5 min buffer)."""
        tokens = FyersTokenStore.load_tokens(encrypted)
        expires_at = datetime.fromisoformat(tokens["expires_at"])
        # Consider expired if < 5 minutes remain
        return datetime.now(timezone.utc) >= (expires_at - timedelta(minutes=5))
    
    @staticmethod
    async def refresh_if_needed(encrypted: str, oauth: FyersOAuth2) -> tuple[str, bool]:
        """Refresh token if expired. Returns (new_encrypted_data, was_refreshed)."""
        tokens = FyersTokenStore.load_tokens(encrypted)
        
        if not FyersTokenStore.is_token_expired(encrypted):
            return encrypted, False  # Still valid
        
        # Token expired; refresh it
        new_tokens = await oauth.refresh_access_token(tokens["refresh_token"])
        new_encrypted = FyersTokenStore.store_tokens(
            access_token=new_tokens["access_token"],
            refresh_token=new_tokens["refresh_token"],
            expires_in=new_tokens["expires_in"],
            client_id=tokens["client_id"],
        )
        return new_encrypted, True
