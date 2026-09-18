from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class OrderRequest:
    symbol: str
    exchange: str
    side: str  # BUY / SELL
    quantity: int
    order_type: str  # MARKET / LIMIT / STOP_LOSS / STOP_LOSS_MARKET
    price: float | None = None
    product_type: str = "INTRADAY"
    correlation_id: str | None = None
    security_id: str | None = None
    exchange_segment: str | None = None
    trigger_price: float | None = None


@dataclass
class OrderResponse:
    order_id: str
    status: str
    broker_order_id: str | None = None
    message: str | None = None


class BrokerAdapter(ABC):
    """Unified interface for Dhan and Groww broker APIs."""

    @abstractmethod
    async def authenticate(self, credentials: dict[str, Any]) -> bool:
        """Validate credentials and obtain access token."""

    @abstractmethod
    async def get_funds(self) -> dict[str, Any]:
        """Return available margin and funds."""

    @abstractmethod
    async def get_holdings(self) -> list[dict[str, Any]]:
        """Return equity holdings."""

    @abstractmethod
    async def get_positions(self) -> list[dict[str, Any]]:
        """Return open positions."""

    @abstractmethod
    async def get_orders(self) -> list[dict[str, Any]]:
        """Return today's order book."""

    @abstractmethod
    async def place_order(self, order: OrderRequest) -> OrderResponse:
        """Place a new order."""

    @abstractmethod
    async def modify_order(self, order_id: str, changes: dict[str, Any]) -> OrderResponse:
        """Modify a pending order."""

    @abstractmethod
    async def cancel_order(self, order_id: str) -> OrderResponse:
        """Cancel a pending order."""

    @abstractmethod
    async def get_market_quote(self, symbols: list[str]) -> dict[str, Any]:
        """Fetch LTP / quote for symbols."""

    @abstractmethod
    async def health_check(self) -> bool:
        """Verify broker connection is alive."""
