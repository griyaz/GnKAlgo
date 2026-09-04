"""Server-side NSE market-status logic.

Deliberately more than a naive ``09:15<=t<=15:30`` check: weekends and
configured holidays resolve to CLOSED/HOLIDAY, and the calendar source is
pluggable so a real NSE trading-calendar/holiday feed can replace the static
config later without touching callers.
"""

from __future__ import annotations

from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from app.config import settings
from app.market_data.models import MarketStatus

IST = ZoneInfo("Asia/Kolkata")

# Standard NSE equity session (Asia/Kolkata).
PRE_OPEN_START = time(9, 0)
REGULAR_OPEN = time(9, 15)
REGULAR_CLOSE = time(15, 30)


def _holidays() -> set[str]:
    """Holiday calendar source. Swap this for a DB/NSE-calendar lookup later."""
    return settings.market_holiday_set


def is_holiday(day: date) -> bool:
    return day.isoformat() in _holidays()


def compute_market_status(now: datetime | None = None) -> MarketStatus:
    """Return the current :class:`MarketStatus` for the NSE equity session."""
    ist_now = (now or datetime.now(IST)).astimezone(IST)
    day = ist_now.date()

    # Saturday=5, Sunday=6
    if ist_now.weekday() >= 5:
        return MarketStatus.CLOSED
    if is_holiday(day):
        return MarketStatus.HOLIDAY

    t = ist_now.time()
    if t < PRE_OPEN_START:
        return MarketStatus.CLOSED
    if PRE_OPEN_START <= t < REGULAR_OPEN:
        return MarketStatus.PRE_OPEN
    if REGULAR_OPEN <= t <= REGULAR_CLOSE:
        return MarketStatus.OPEN
    return MarketStatus.CLOSED


def is_market_open(now: datetime | None = None) -> bool:
    return compute_market_status(now) == MarketStatus.OPEN


def status_label(status: MarketStatus) -> str:
    return {
        MarketStatus.PRE_OPEN: "Pre-Open",
        MarketStatus.OPEN: "Market Open",
        MarketStatus.CLOSED: "Market Closed",
        MarketStatus.HOLIDAY: "Market Holiday",
        MarketStatus.UNKNOWN: "Market",
    }[status]
