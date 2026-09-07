import math
import random
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.services.instrument_service import instrument_service
from app.services.redis_cache import cache_get, cache_set

IST = ZoneInfo("Asia/Kolkata")

INTERVAL_SECONDS = {
    "1m": 60,
    "3m": 180,
    "5m": 300,
    "15m": 900,
    "30m": 1800,
    "1H": 3600,
    "4H": 14400,
    "1D": 86400,
    "1W": 604800,
}

BASE_PRICES = {
    "NIFTY50": 24175.0,
    "NIFTY": 24175.0,
    "BANKNIFTY": 57496.0,
    "RELIANCE": 2850.0,
    "TCS": 4100.0,
    "INFY": 1850.0,
    "HDFCBANK": 1680.0,
    "ICICIBANK": 1250.0,
    "SBIN": 820.0,
    "FINNIFTY": 27420.0,
    "SENSEX": 79820.0,
}


def _interval_sec(interval: str) -> int:
    return INTERVAL_SECONDS.get(interval, 300)


def _generate_mock_candles(symbol: str, interval: str, count: int = 500) -> list[dict]:
    base = BASE_PRICES.get(symbol.upper(), 1000.0)
    step = _interval_sec(interval)
    now = datetime.now(IST)
    candles = []
    price = base
    t = int(now.timestamp()) - step * count
    for _ in range(count):
        change = random.uniform(-0.003, 0.003) * price
        o = price
        c = max(0.01, price + change)
        h = max(o, c) * (1 + random.uniform(0, 0.001))
        l = min(o, c) * (1 - random.uniform(0, 0.001))
        vol = int(random.uniform(50000, 250000)) if symbol.upper() not in ("NIFTY50", "NIFTY", "SENSEX", "INDIAVIX") else None
        candles.append({
            "time": t,
            "open": round(o, 2),
            "high": round(h, 2),
            "low": round(l, 2),
            "close": round(c, 2),
            "volume": vol,
        })
        price = c
        t += step
    return candles


class CandleService:
    async def get_candles(
        self,
        db: AsyncSession,
        symbol: str,
        exchange: str,
        interval: str,
        adapter=None,
        count: int = 500,
    ) -> dict:
        inst = await instrument_service.get(db, symbol, exchange)
        if not inst:
            inst = instrument_service.curated_fallback(symbol)
        if not inst:
            inst = {
                "symbol": symbol.upper(),
                "exchange": exchange,
                "segment": "EQUITY",
                "security_id": symbol,
            }

        cache_key = f"candles:{inst['symbol']}:{exchange}:{interval}:{count}"
        cached = await cache_get(cache_key)
        if cached:
            cached["source"] = f"{cached.get('source', 'unknown')}+redis"
            return cached

        use_mock = (settings.app_env != "production" or settings.debug) and not adapter
        candles: list[dict] = []

        if adapter:
            try:
                security_id = inst["security_id"]
                # Upstox accepts a provider instrument key when one is
                # available in the shared instrument master.
                if adapter.__class__.__name__.lower().startswith("upstox") and "|" in str(
                    inst.get("instrument_token", "")
                ):
                    security_id = inst["instrument_token"]
                candles = await adapter.get_historical_candles(
                    security_id=security_id,
                    exchange=inst.get("exchange", exchange),
                    segment=inst.get("segment", "EQUITY"),
                    interval=interval,
                )
            except Exception:
                candles = []

        if not candles and use_mock:
            candles = _generate_mock_candles(inst["symbol"], interval, count)
            source = "mock_dev"
        elif candles:
            source = "dhan"
        else:
            source = "empty"

        # Normalize ascending, unique timestamps
        seen = set()
        normalized = []
        for c in sorted(candles, key=lambda x: x["time"]):
            if c["time"] in seen:
                continue
            seen.add(c["time"])
            if not all(k in c for k in ("open", "high", "low", "close")):
                continue
            normalized.append(c)

        result = {
            "symbol": inst["symbol"],
            "exchange": inst.get("exchange", exchange),
            "interval": interval,
            "candles": normalized,
            "source": source,
            "security_id": inst.get("security_id"),
        }
        if normalized:
            await cache_set(cache_key, result, settings.cache_candles_ttl_seconds)
        return result


candle_service = CandleService()
