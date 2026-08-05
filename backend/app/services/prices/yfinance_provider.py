"""yfinance-backed price provider.

yfinance scrapes an unofficial Yahoo endpoint. It is free and needs no API
key, which is why it is the default, but it can and does break. Every method
here is written to fail softly: partial results are returned, exceptions are
contained per ticker, and the caller is expected to fall back to the last
stored price for anything missing.
"""

from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal

from app.money import parse_decimal, quantize_price
from app.services.prices.base import Quote, SecurityInfo

logger = logging.getLogger(__name__)

# A window rather than a single day: markets close at different times, and
# weekends and holidays leave gaps. We take the most recent real close within
# it, which is exactly "the latest daily close".
LOOKBACK_PERIOD = "7d"


class YFinanceProvider:
    def get_latest_close(self, tickers: list[str]) -> dict[str, Quote]:
        if not tickers:
            return {}

        import yfinance as yf

        try:
            data = yf.download(
                tickers,
                period=LOOKBACK_PERIOD,
                progress=False,
                auto_adjust=False,
                # Keep the column shape identical for one ticker and many,
                # so the parsing below has only one case to handle.
                group_by="column",
            )
        except Exception:
            logger.exception("Price download failed for %s", tickers)
            return {}

        if data is None or data.empty:
            logger.warning("Price download returned no data for %s", tickers)
            return {}

        try:
            closes = data["Close"]
        except KeyError:
            logger.warning("Price data missing a Close column for %s", tickers)
            return {}

        results: dict[str, Quote] = {}
        for ticker in tickers:
            try:
                series = closes[ticker] if ticker in closes else closes
                # The most recent row is often NaN — the market has not closed
                # yet today. Drop the gaps and take the last genuine close.
                series = series.dropna()
                if series.empty:
                    logger.warning("No close price available for %s", ticker)
                    continue

                as_of = series.index[-1]
                results[ticker] = Quote(
                    ticker=ticker,
                    close=quantize_price(parse_decimal(float(series.iloc[-1]))),
                    as_of=as_of.date() if hasattr(as_of, "date") else date.today(),
                    currency=self._currency_for(ticker),
                )
            except Exception:
                # One bad ticker must not cost us the others.
                logger.exception("Could not parse price for %s", ticker)

        return results

    def _currency_for(self, ticker: str) -> str:
        """Quote currency, defaulting to USD if the lookup fails."""
        info = self.lookup(ticker)
        return info.currency if info else "USD"

    def lookup(self, ticker: str) -> SecurityInfo | None:
        import yfinance as yf

        ticker = ticker.strip().upper()
        if not ticker:
            return None

        try:
            handle = yf.Ticker(ticker)
            fast = handle.fast_info
            currency = fast.get("currency")
            last_price = fast.get("lastPrice")

            # Yahoo returns an empty shell rather than an error for unknown
            # symbols, so "no currency and no price" is how a typo presents.
            if not currency and last_price is None:
                return None

            name = ticker
            try:
                info = handle.info
                # Yahoo pads and double-spaces some names ("SAP SE      I").
                raw_name = info.get("shortName") or info.get("longName") or ticker
                name = " ".join(str(raw_name).split())
                quote_type = (info.get("quoteType") or "EQUITY").lower()
            except Exception:
                # `.info` is the slowest and least reliable call; a missing
                # display name should never block adding a valid holding.
                quote_type = (fast.get("quoteType") or "EQUITY").lower()

            asset_type = {
                "equity": "stock",
                "etf": "etf",
                "mutualfund": "fund",
            }.get(quote_type, "other")

            return SecurityInfo(
                ticker=ticker,
                name=name,
                currency=(currency or "USD").upper(),
                exchange=fast.get("exchange"),
                asset_type=asset_type,
            )
        except Exception:
            logger.exception("Ticker lookup failed for %s", ticker)
            return None

    def get_fx_rate(self, base: str, quote: str) -> Decimal | None:
        """Rate to multiply a `base` amount by to get `quote`."""
        base, quote = base.upper(), quote.upper()
        if base == quote:
            return Decimal(1)

        import yfinance as yf

        try:
            series = (
                yf.Ticker(f"{base}{quote}=X")
                .history(period=LOOKBACK_PERIOD)["Close"]
                .dropna()
            )
            if series.empty:
                logger.warning("No FX data for %s%s", base, quote)
                return None
            return quantize_price(parse_decimal(float(series.iloc[-1])))
        except Exception:
            logger.exception("FX lookup failed for %s%s", base, quote)
            return None
