"""The price provider contract.

Everything that touches the network lives behind this interface. The rest of
the app never imports yfinance, so swapping in Alpha Vantage or Finnhub later
means writing one new class, not a refactor — which matters, because yfinance
scrapes an unofficial endpoint and does periodically break.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Protocol, runtime_checkable


class PriceProviderError(Exception):
    """Any failure to reach or parse the upstream source."""


@dataclass(frozen=True)
class Quote:
    ticker: str
    close: Decimal
    as_of: date
    currency: str


@dataclass(frozen=True)
class SecurityInfo:
    """What we learn about a symbol when the user first adds it."""

    ticker: str
    name: str
    currency: str
    exchange: str | None = None
    asset_type: str = "stock"


@runtime_checkable
class PriceProvider(Protocol):
    def get_latest_close(self, tickers: list[str]) -> dict[str, Quote]:
        """Latest daily close per ticker.

        Implementations must be partial-failure tolerant: return what could be
        fetched and simply omit the rest, rather than raising and losing the
        good data. Callers fall back to the last stored price for anything
        missing.
        """
        ...

    def lookup(self, ticker: str) -> SecurityInfo | None:
        """Resolve a symbol to its name, currency and exchange.

        Returns None if the symbol does not exist, which is how the API tells
        a typo from a working ticker before saving a holding.
        """
        ...

    def get_fx_rate(self, base: str, quote: str) -> Decimal | None:
        """Rate to multiply a `base` amount by to get `quote`."""
        ...
