from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", "../.env"), env_file_encoding="utf-8", extra="ignore")

    app_name: str = "GnKAlgo"
    app_env: str = "development"
    debug: bool = False
    secret_key: str = "dev-secret-change-in-production"
    encryption_key: str = "dev-encryption-key-32bytes-min!!"
    rate_limit_enabled: bool = True

    database_url: str = "sqlite+aiosqlite:///./gnkalgo.db"
    redis_url: str = "redis://localhost:6379/0"

    jwt_access_token_expire_minutes: int = 15
    jwt_refresh_token_expire_days: int = 7
    jwt_algorithm: str = "HS256"

    frontend_url: str = "http://localhost:3000"
    allowed_origins: str = "http://localhost:3000,https://www.gnkalgo.com,https://gnkalgo.com,https://api.gnkalgo.com"

    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = "noreply@gnkalgo.com"
    smtp_starttls: bool = True
    smtp_ssl: bool = False
    email_verification_required: bool = False

    dhan_api_base_url: str = "https://api.dhan.co/v2"
    dhan_feed_ws_url: str = "wss://api-feed.dhan.co"
    dhan_static_ip: str = ""
    cookie_secure: bool = False

    instrument_master_url: str = "https://images.dhan.co/api-data/api-scrip-master.csv"
    instrument_sync_enabled: bool = True
    instrument_sync_interval_hours: int = 24

    groww_api_base_url: str = "https://api.groww.in"
    groww_client_id: str = ""
    groww_client_secret: str = ""

    # Order-execution REST endpoints for the optional FYERS/Upstox broker adapters.
    # (Separate from the market-data feed config further below.)
    fyers_api_base_url: str = "https://api-t1.fyers.in/api/v3"
    upstox_api_base_url: str = "https://api.upstox.com/v2"

    ml_service_url: str = "http://localhost:8001"
    ml_service_token: str = ""
    backend_public_url: str = "http://localhost:8000"
    admin_emails: str = ""
    upi_vpa: str = "gnkalgo@upi"
    upi_payee_name: str = "GNK ALGO"
    strategy_scheduler_tick_seconds: int = 60
    support_email: str = "support@gnkalgo.com"
    auto_renew_lead_hours: int = 24
    billing_scheduler_tick_seconds: int = 3600

    cache_candles_ttl_seconds: int = 120
    cache_news_ttl_seconds: int = 300
    news_provider: str = "finnhub"
    finnhub_api_key: str = ""
    finnhub_base_url: str = "https://finnhub.io/api/v1"

    # ------------------------------------------------------------------
    # Live market ticker (LiveMarketTicker) — see docs/LIVE_MARKET_TICKER.md
    # ------------------------------------------------------------------
    # Primary upstream provider for the index ticker feed: fyers | dhan | upstox | mock
    market_data_provider: str = "fyers"
    # Only switch to a fallback provider when the primary is unavailable AND this is true.
    market_data_failover_enabled: bool = False
    # Mark a tick stale when no upstream update arrives within this many seconds (market open).
    market_data_stale_seconds: int = 10
    # Deterministic demo feed for local dev/tests. Never a silent production fallback.
    market_data_mock_mode: bool = False
    # Redis TTL for cached ticker snapshots while the market is open (seconds).
    market_data_cache_ttl_seconds: int = 60
    # Require an authenticated GnKAlgo session to open the ticker WebSocket.
    market_data_require_auth: bool = True
    # Comma-separated NSE holiday dates (YYYY-MM-DD, Asia/Kolkata) treated as HOLIDAY.
    market_holidays: str = ""
    # Optional JSON overrides for per-provider index symbols. See symbols.py.
    # e.g. {"NIFTY50": {"fyers": "NSE:NIFTY50-INDEX", "dhan": "IDX_I:13"}}
    market_data_symbol_overrides: str = ""

    # FYERS API v3 (primary). Backend-only — never expose via NEXT_PUBLIC_*.
    fyers_client_id: str = ""
    fyers_access_token: str = ""

    # Dhan market feed (optional fallback). Separate from Dhan execution/orders.
    dhan_market_data_enabled: bool = False
    dhan_client_id: str = ""
    dhan_access_token: str = ""

    # Upstox Market Data Feed V3 (optional fallback).
    upstox_market_data_enabled: bool = False
    upstox_access_token: str = ""

    @property
    def market_holiday_set(self) -> set[str]:
        return {d.strip() for d in self.market_holidays.split(",") if d.strip()}

    @property
    def admin_email_list(self) -> list[str]:
        return [e.strip().lower() for e in self.admin_emails.split(",") if e.strip()]

    @property
    def origins_list(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]

    @property
    def cors_origin_regex(self) -> str:
        """Origin regex for CORS, in addition to the explicit ``origins_list``.

        Production is locked to the gnkalgo.com domains. Outside production we
        also accept any localhost / 127.0.0.1 port over http, so the dev UI works
        no matter which loopback host or port it is served from (e.g. when 3000
        is busy and Next.js falls back to another port, or the browser is pointed
        at 127.0.0.1 instead of localhost). Without this, those origins are
        rejected by CORS and every authenticated fetch fails with
        "Failed to fetch" in the browser.
        """
        prod = r"https://([a-z0-9-]+\.)?gnkalgo\.com"
        if self.app_env.strip().lower() in {"production", "prod"}:
            return prod
        local = r"http://(localhost|127\.0\.0\.1)(:\d+)?"
        return f"{prod}|{local}"

    @property
    def smtp_configured(self) -> bool:
        """Return true only when SMTP has usable, non-placeholder settings.

        Development commonly starts from ``.env.example``. Treating its sample
        values as credentials blocks unverified logins without being able to
        deliver the verification message.
        """
        required = (self.smtp_host, self.smtp_from)
        if not all(value.strip() for value in required):
            return False
        if self.smtp_user and not self.smtp_password.strip():
            return False
        values = (self.smtp_host, self.smtp_user, self.smtp_password, self.smtp_from)
        placeholders = ("replace-", "your-", "example", "changeme")
        return not any(
            value and any(marker in value.strip().lower() for marker in placeholders)
            for value in values
        )


settings = Settings()
