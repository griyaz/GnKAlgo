"""Common provider interface + reconnect backoff.

Every provider normalizes its broker-specific packets into the internal
:class:`~app.market_data.models.Tick` model and exposes the same async
interface so :class:`~app.market_data.manager.MarketDataManager` can treat them
interchangeably.
"""

from __future__ import annotations

import abc
import random
from collections.abc import AsyncIterator, Iterable

from app.market_data.models import Tick
from app.market_data.symbols import IndexSymbol


class ProviderError(Exception):
    """Base class for provider errors."""


class ProviderUnavailable(ProviderError):
    """Provider cannot start (missing SDK, disabled, or not configured)."""


class ProviderAuthError(ProviderError):
    """Provider rejected the supplied credentials."""


class MarketDataProvider(abc.ABC):
    """Abstract upstream market-data provider."""

    name: str = "base"

    @abc.abstractmethod
    async def connect(self) -> None:
        """Authenticate and open the upstream connection."""

    @abc.abstractmethod
    async def disconnect(self) -> None:
        """Close the upstream connection and release resources."""

    @abc.abstractmethod
    async def subscribe(self, instruments: Iterable[IndexSymbol]) -> None:
        """Subscribe to the given instruments."""

    @abc.abstractmethod
    async def unsubscribe(self, instruments: Iterable[IndexSymbol]) -> None:
        """Unsubscribe from the given instruments."""

    @abc.abstractmethod
    def stream(self) -> AsyncIterator[Tick]:
        """Yield normalized ticks until the connection drops.

        Implementations should return/raise when the socket closes so the
        manager can reconnect.
        """
        raise NotImplementedError


class BackoffPolicy:
    """Exponential backoff with jitter and reset-after-stable.

    Delay schedule (seconds): 1, 2, 4, 8, 15, 30 (capped). Full jitter is
    applied so many workers do not reconnect in lockstep, and the delay resets
    once a connection has stayed up long enough to be considered stable.
    """

    STEPS = (1.0, 2.0, 4.0, 8.0, 15.0, 30.0)

    def __init__(self, stable_after_seconds: float = 30.0) -> None:
        self._index = 0
        self.stable_after_seconds = stable_after_seconds

    def reset(self) -> None:
        self._index = 0

    def next_delay(self) -> float:
        base = self.STEPS[min(self._index, len(self.STEPS) - 1)]
        if self._index < len(self.STEPS) - 1:
            self._index += 1
        # Full jitter in [0.5*base, base] avoids a busy loop while keeping the
        # backoff bounded and de-synchronised across processes.
        return round(random.uniform(base * 0.5, base), 3)
