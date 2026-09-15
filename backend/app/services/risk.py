from datetime import datetime, time
from zoneinfo import ZoneInfo

from app.config import settings
from app.services.candle_service import BASE_PRICES
from app.services.market_quote_cache import get_by_symbol

IST = ZoneInfo("Asia/Kolkata")
MARKET_OPEN = time(9, 15)
MARKET_CLOSE = time(15, 30)

# Last-resort notional when a MARKET order has no fill price, quote, or curated
# base. Zero would silently disable daily-loss circuit breakers.
UNKNOWN_SYMBOL_RISK_PRICE = 1000.0


def notional_price(symbol: str, stored_price: float | None) -> float:
    """Price used for daily-loss / exposure checks.

    Live MARKET orders persist ``price=None`` (the broker wire value is 0).
    Treating that as zero made ``max_daily_loss`` and ``live_daily_loss_limit``
    ignore the entire SMC and Quick Order MARKET path.
    """
    try:
        if stored_price is not None and float(stored_price) > 0:
            return float(stored_price)
    except (TypeError, ValueError):
        pass
    cached = get_by_symbol(symbol)
    if cached:
        try:
            ltp = float(cached.get("ltp") or 0)
            if ltp > 0:
                return ltp
        except (TypeError, ValueError):
            pass
    base = BASE_PRICES.get((symbol or "").upper())
    if base and float(base) > 0:
        return float(base)
    return UNKNOWN_SYMBOL_RISK_PRICE


class RiskRejection(Exception):
    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


def is_market_hours(now: datetime | None = None) -> bool:
    current = now or datetime.now(IST)
    if current.tzinfo is None:
        current = current.replace(tzinfo=IST)
    else:
        current = current.astimezone(IST)
    if current.weekday() >= 5 or current.date().isoformat() in settings.market_holiday_set:
        return False
    t = current.timetz().replace(tzinfo=None)
    return MARKET_OPEN <= t <= MARKET_CLOSE


def validate_order(
    *,
    quantity: int,
    max_quantity: int = 500,
    paper_mode: bool = True,
    now: datetime | None = None,
) -> None:
    if quantity <= 0:
        raise RiskRejection("Quantity must be greater than zero")
    if quantity > max_quantity:
        raise RiskRejection(f"Quantity exceeds max allowed ({max_quantity})")
    if not paper_mode and not is_market_hours(now):
        raise RiskRejection("Live orders are allowed only during NSE market hours (09:15–15:30 IST)")
