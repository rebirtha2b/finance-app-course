"""A scriptable stand-in for the price provider.

Tests must never hit the network: it makes them slow, flaky, and dependent on
what the market happened to do today. This fake lets each test state exactly
what the upstream returns, including the failure modes that matter — a symbol
that does not exist, a total outage, and a partial response.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.services.prices.base import Quote, SecurityInfo


class FakeProvider:
    def __init__(self) -> None:
        self.quotes: dict[str, Quote] = {}
        self.securities: dict[str, SecurityInfo] = {}
        self.fx: dict[tuple[str, str], Decimal] = {}
        # Set to raise from every method, simulating a full outage.
        self.raise_on_calls = False
        # Tickers to silently omit from get_latest_close, as a real partial
        # failure looks (yfinance returns the rows it managed to fetch).
        self.omit: set[str] = set()
        self.call_count = 0

    # -- scripting helpers -------------------------------------------------

    def add_security(
        self,
        ticker: str,
        *,
        name: str = "Test Corp",
        currency: str = "USD",
        exchange: str = "NMS",
        price: str | None = None,
        as_of: date | None = None,
    ) -> None:
        self.securities[ticker] = SecurityInfo(
            ticker=ticker, name=name, currency=currency, exchange=exchange
        )
        if price is not None:
            self.set_price(ticker, price, as_of or date(2026, 8, 4), currency)

    def set_price(
        self, ticker: str, close: str, as_of: date, currency: str = "USD"
    ) -> None:
        self.quotes[ticker] = Quote(
            ticker=ticker, close=Decimal(close), as_of=as_of, currency=currency
        )

    def set_fx(self, base: str, quote: str, rate: str) -> None:
        self.fx[(base.upper(), quote.upper())] = Decimal(rate)

    # -- PriceProvider -----------------------------------------------------

    def get_latest_close(self, tickers: list[str]) -> dict[str, Quote]:
        self.call_count += 1
        if self.raise_on_calls:
            raise RuntimeError("simulated upstream outage")
        return {
            t: self.quotes[t]
            for t in tickers
            if t in self.quotes and t not in self.omit
        }

    def lookup(self, ticker: str) -> SecurityInfo | None:
        if self.raise_on_calls:
            raise RuntimeError("simulated upstream outage")
        return self.securities.get(ticker.strip().upper())

    def get_fx_rate(self, base: str, quote: str) -> Decimal | None:
        if self.raise_on_calls:
            raise RuntimeError("simulated upstream outage")
        if base.upper() == quote.upper():
            return Decimal(1)
        return self.fx.get((base.upper(), quote.upper()))
