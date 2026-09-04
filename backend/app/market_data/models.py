"""Normalized market-data models shared by every provider.

Every broker packet is normalized into a single :class:`Tick` before it reaches
Redis or the frontend, so the rest of the system never sees provider-specific
shapes. Financial values are kept as :class:`~decimal.Decimal` internally to
avoid float drift; they are converted to plain numbers only at the JSON edge.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Any, Optional


class MarketStatus(str, Enum):
    PRE_OPEN = "PRE_OPEN"
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    HOLIDAY = "HOLIDAY"
    UNKNOWN = "UNKNOWN"


def to_decimal(value: Any) -> Optional[Decimal]:
    """Best-effort convert broker numeric fields to Decimal, or None."""
    if value is None or value == "":
        return None
    if isinstance(value, Decimal):
        return value
    try:
        # str() first so float inputs like 25123.5 do not carry binary noise.
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _num(value: Optional[Decimal]) -> Optional[float]:
    return float(value) if value is not None else None


def compute_change(
    ltp: Optional[Decimal], previous_close: Optional[Decimal]
) -> tuple[Optional[Decimal], Optional[Decimal]]:
    """Return ``(change, change_percent)`` computed against previous close.

    Change is always ``ltp - previous_close`` — never against an arbitrary
    baseline. Division by zero (or missing values) is handled safely.
    """
    if ltp is None or previous_close is None:
        return None, None
    change = ltp - previous_close
    if previous_close == 0:
        return change, Decimal("0")
    change_percent = (change / previous_close) * Decimal("100")
    return change, change_percent


@dataclass
class Tick:
    """One normalized snapshot for a single instrument."""

    symbol: str  # internal id, e.g. "NIFTY50"
    display_name: str  # e.g. "NIFTY 50"
    exchange: str  # e.g. "NSE"
    provider: str  # e.g. "FYERS"

    ltp: Optional[Decimal] = None
    previous_close: Optional[Decimal] = None
    open: Optional[Decimal] = None
    high: Optional[Decimal] = None
    low: Optional[Decimal] = None

    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    market_status: MarketStatus = MarketStatus.UNKNOWN
    is_stale: bool = False

    @property
    def change(self) -> Optional[Decimal]:
        return compute_change(self.ltp, self.previous_close)[0]

    @property
    def change_percent(self) -> Optional[Decimal]:
        return compute_change(self.ltp, self.previous_close)[1]

    # -- serialization -------------------------------------------------
    def to_public_dict(self) -> dict[str, Any]:
        """JSON-safe payload for Redis and the frontend (numbers, not Decimal)."""
        change, change_percent = compute_change(self.ltp, self.previous_close)
        return {
            "symbol": self.symbol,
            "display_name": self.display_name,
            "exchange": self.exchange,
            "provider": self.provider,
            "ltp": _num(self.ltp),
            "previous_close": _num(self.previous_close),
            "change": _num(change),
            "change_percent": (
                round(float(change_percent), 2) if change_percent is not None else None
            ),
            "open": _num(self.open),
            "high": _num(self.high),
            "low": _num(self.low),
            "timestamp": self.timestamp.astimezone(timezone.utc).isoformat(),
            "market_status": self.market_status.value,
            "is_stale": self.is_stale,
        }

    @classmethod
    def from_public_dict(cls, data: dict[str, Any]) -> "Tick":
        ts = data.get("timestamp")
        try:
            timestamp = (
                datetime.fromisoformat(ts) if ts else datetime.now(timezone.utc)
            )
        except (ValueError, TypeError):
            timestamp = datetime.now(timezone.utc)
        status = data.get("market_status")
        try:
            market_status = MarketStatus(status) if status else MarketStatus.UNKNOWN
        except ValueError:
            market_status = MarketStatus.UNKNOWN
        return cls(
            symbol=data["symbol"],
            display_name=data.get("display_name", data["symbol"]),
            exchange=data.get("exchange", "NSE"),
            provider=data.get("provider", "UNKNOWN"),
            ltp=to_decimal(data.get("ltp")),
            previous_close=to_decimal(data.get("previous_close")),
            open=to_decimal(data.get("open")),
            high=to_decimal(data.get("high")),
            low=to_decimal(data.get("low")),
            timestamp=timestamp,
            market_status=market_status,
            is_stale=bool(data.get("is_stale", False)),
        )

    def merged_with(self, other: "Tick") -> "Tick":
        """Merge a fresh partial tick onto this one, keeping known prior fields.

        Providers send LTP and previous-close in separate packets, so we retain
        the last known previous_close/OHLC when a packet omits them.
        """
        return Tick(
            symbol=self.symbol,
            display_name=self.display_name,
            exchange=self.exchange,
            provider=other.provider or self.provider,
            ltp=other.ltp if other.ltp is not None else self.ltp,
            previous_close=(
                other.previous_close
                if other.previous_close is not None
                else self.previous_close
            ),
            open=other.open if other.open is not None else self.open,
            high=other.high if other.high is not None else self.high,
            low=other.low if other.low is not None else self.low,
            timestamp=other.timestamp,
            market_status=other.market_status,
            is_stale=other.is_stale,
        )
