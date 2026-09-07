from datetime import datetime, time
from zoneinfo import ZoneInfo

from app.config import settings

IST = ZoneInfo("Asia/Kolkata")
MARKET_OPEN = time(9, 15)
MARKET_CLOSE = time(15, 30)


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
