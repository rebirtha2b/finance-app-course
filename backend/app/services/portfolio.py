"""Portfolio pricing and valuation.

The rule that shapes this module: **a failed price fetch must never show you a
zero.** yfinance is an unofficial scraper and will occasionally return nothing.
When that happens we keep serving the last close we successfully stored and
tell the user how old it is. A portfolio that reads "€0.00" because a scrape
failed is worse than useless — it looks like you lost everything.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.config import settings
from app.models import (
    Holding,
    PortfolioSnapshot,
    PriceSnapshot,
    Security,
    utcnow,
)
from app.money import quantize_money, to_cents
from app.services import fx
from app.services.prices import get_provider

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------ pricing


@dataclass
class RefreshResult:
    prices_updated: int
    fx_updated: int
    failed_tickers: list[str] = field(default_factory=list)
    failed_fx: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.failed_tickers and not self.failed_fx


def store_price(
    session: Session, security: Security, close: Decimal, on: date, currency: str
) -> PriceSnapshot:
    existing = session.scalar(
        select(PriceSnapshot).where(
            PriceSnapshot.security_id == security.id, PriceSnapshot.date == on
        )
    )
    if existing:
        existing.close_price = close
        existing.currency = currency
        existing.fetched_at = utcnow()
        return existing

    snapshot = PriceSnapshot(
        security_id=security.id,
        date=on,
        close_price=close,
        currency=currency,
        fetched_at=utcnow(),
    )
    session.add(snapshot)
    return snapshot


def latest_price(
    session: Session, security_id: int, on: date | None = None
) -> PriceSnapshot | None:
    """Most recent stored close on or before `on` — the stale-fallback source."""
    stmt = select(PriceSnapshot).where(PriceSnapshot.security_id == security_id)
    if on is not None:
        stmt = stmt.where(PriceSnapshot.date <= on)
    return session.scalar(stmt.order_by(PriceSnapshot.date.desc()).limit(1))


def previous_price(
    session: Session, security_id: int, before: date
) -> PriceSnapshot | None:
    """The close before `before`, used for the day-change figure."""
    return session.scalar(
        select(PriceSnapshot)
        .where(PriceSnapshot.security_id == security_id, PriceSnapshot.date < before)
        .order_by(PriceSnapshot.date.desc())
        .limit(1)
    )


def refresh_prices(session: Session) -> RefreshResult:
    """Fetch the latest close for every held security, plus any FX needed."""
    securities = list(
        session.scalars(select(Security).join(Holding).distinct())
    )
    if not securities:
        return RefreshResult(prices_updated=0, fx_updated=0)

    by_ticker = {s.ticker: s for s in securities}
    provider = get_provider()

    try:
        quotes = provider.get_latest_close(list(by_ticker))
    except Exception:
        logger.exception("Price refresh failed entirely")
        quotes = {}

    updated = 0
    for ticker, security in by_ticker.items():
        quote = quotes.get(ticker)
        if quote is None or quote.close <= 0:
            continue
        # Trust the provider's currency, but never let it silently flip an
        # existing security's currency — that would corrupt past valuations.
        currency = security.currency or quote.currency
        store_price(session, security, quote.close, quote.as_of, currency)
        updated += 1

    failed = sorted(set(by_ticker) - set(quotes))

    currencies = {s.currency for s in securities if s.currency}
    failed_fx = fx.refresh_rates(session, currencies, settings.base_currency)
    fx_updated = len(currencies - {settings.base_currency}) - len(failed_fx)

    session.commit()

    if failed:
        logger.warning("No fresh price for: %s (keeping last known)", ", ".join(failed))

    return RefreshResult(
        prices_updated=updated,
        fx_updated=max(fx_updated, 0),
        failed_tickers=failed,
        failed_fx=failed_fx,
    )


# --------------------------------------------------------------- valuation


@dataclass
class HoldingValue:
    holding_id: int
    security_id: int
    ticker: str
    name: str
    currency: str
    quantity: Decimal
    # None when we have never managed to fetch a price for this security.
    price: Decimal | None
    price_date: date | None
    value_native: Decimal | None
    value_base: Decimal | None
    day_change_base: Decimal | None
    day_change_percent: float | None
    cost_basis_base: Decimal | None
    gain_base: Decimal | None
    gain_percent: float | None
    allocation_percent: float
    # True when the price we are showing is not from the most recent close we
    # know about across the portfolio.
    stale: bool


@dataclass
class PortfolioValuation:
    holdings: list[HoldingValue]
    total_value_base: Decimal
    total_cost_base: Decimal | None
    total_gain_base: Decimal | None
    total_gain_percent: float | None
    day_change_base: Decimal
    base_currency: str
    # Oldest price date in use — what the "prices as of" banner shows.
    prices_as_of: date | None
    has_stale_prices: bool
    missing_prices: list[str]


def value_portfolio(session: Session, on: date | None = None) -> PortfolioValuation:
    on = on or date.today()
    base = settings.base_currency

    holdings = list(
        session.scalars(select(Holding).options(selectinload(Holding.security)))
    )

    rows: list[HoldingValue] = []
    missing: list[str] = []
    price_dates: list[date] = []

    for holding in holdings:
        security = holding.security
        snapshot = latest_price(session, security.id, on)

        if snapshot is None:
            # Never priced: show the holding with blank values rather than
            # dropping it or pretending it is worth nothing.
            missing.append(security.ticker)
            rows.append(
                HoldingValue(
                    holding_id=holding.id,
                    security_id=security.id,
                    ticker=security.ticker,
                    name=security.name,
                    currency=security.currency,
                    quantity=holding.quantity,
                    price=None,
                    price_date=None,
                    value_native=None,
                    value_base=None,
                    day_change_base=None,
                    day_change_percent=None,
                    cost_basis_base=None,
                    gain_base=None,
                    gain_percent=None,
                    allocation_percent=0.0,
                    stale=True,
                )
            )
            continue

        price_dates.append(snapshot.date)
        # Quantities and prices are exact; the products are rounded to cents
        # here so the API never emits a 28-digit tail like 2678.6120626055...
        value_native = quantize_money(holding.quantity * snapshot.close_price)

        rate = fx.latest_rate(session, security.currency, base, on)
        value_base = (
            quantize_money(holding.quantity * snapshot.close_price * rate)
            if rate is not None
            else None
        )
        if rate is None:
            # We have a price but cannot convert it. Better to surface the
            # holding with no base value than to invent a rate of 1.
            logger.warning(
                "No FX rate %s->%s; %s has no base-currency value",
                security.currency,
                base,
                security.ticker,
            )

        prev = previous_price(session, security.id, snapshot.date)
        day_change_base = None
        day_change_percent = None
        if prev is not None and rate is not None:
            delta_native = (snapshot.close_price - prev.close_price) * holding.quantity
            day_change_base = quantize_money(delta_native * rate)
            if prev.close_price:
                day_change_percent = float(
                    (snapshot.close_price - prev.close_price) / prev.close_price * 100
                )

        cost_basis_base = None
        gain_base = None
        gain_percent = None
        if holding.avg_cost_price is not None and rate is not None:
            cost_basis_base = quantize_money(
                holding.quantity * holding.avg_cost_price * rate
            )
            if value_base is not None:
                gain_base = quantize_money(value_base - cost_basis_base)
                if cost_basis_base:
                    gain_percent = round(float(gain_base / cost_basis_base * 100), 2)

        rows.append(
            HoldingValue(
                holding_id=holding.id,
                security_id=security.id,
                ticker=security.ticker,
                name=security.name,
                currency=security.currency,
                quantity=holding.quantity,
                price=snapshot.close_price,
                price_date=snapshot.date,
                value_native=value_native,
                value_base=value_base,
                day_change_base=day_change_base,
                day_change_percent=day_change_percent,
                cost_basis_base=cost_basis_base,
                gain_base=gain_base,
                gain_percent=gain_percent,
                allocation_percent=0.0,
                stale=False,
            )
        )

    total_value = sum((r.value_base for r in rows if r.value_base is not None), Decimal(0))
    total_cost_values = [r.cost_basis_base for r in rows if r.cost_basis_base is not None]
    total_cost = sum(total_cost_values, Decimal(0)) if total_cost_values else None
    day_change = sum(
        (r.day_change_base for r in rows if r.day_change_base is not None), Decimal(0)
    )

    # Allocation is only meaningful once we know the total.
    for row in rows:
        if row.value_base is not None and total_value:
            row.allocation_percent = round(float(row.value_base / total_value * 100), 2)

    newest = max(price_dates) if price_dates else None
    for row in rows:
        if row.price_date is not None and newest is not None:
            row.stale = row.price_date < newest

    # Summed from the per-holding gains, NOT `total_value - total_cost`.
    # Those differ whenever some holdings have an average cost and others do
    # not: the subtraction would compare the value of every holding against
    # the cost of only the priced-in ones, inflating the gain wildly.
    gain_values = [r.gain_base for r in rows if r.gain_base is not None]
    total_gain = quantize_money(sum(gain_values, Decimal(0))) if gain_values else None
    total_gain_percent = (
        round(float(total_gain / total_cost * 100), 2)
        if total_cost not in (None, Decimal(0)) and total_gain is not None
        else None
    )

    return PortfolioValuation(
        holdings=sorted(
            rows, key=lambda r: r.value_base or Decimal(-1), reverse=True
        ),
        total_value_base=total_value,
        total_cost_base=total_cost,
        total_gain_base=total_gain,
        total_gain_percent=total_gain_percent,
        day_change_base=day_change,
        base_currency=base,
        prices_as_of=min(price_dates) if price_dates else None,
        has_stale_prices=any(r.stale for r in rows) or bool(missing),
        missing_prices=missing,
    )


def record_snapshot(session: Session, on: date | None = None) -> PortfolioSnapshot:
    """Store today's total so the history chart has a series to draw."""
    on = on or date.today()
    valuation = value_portfolio(session, on)

    existing = session.scalar(
        select(PortfolioSnapshot).where(PortfolioSnapshot.date == on)
    )
    total_cents = to_cents(valuation.total_value_base)
    cost_cents = (
        to_cents(valuation.total_cost_base)
        if valuation.total_cost_base is not None
        else None
    )

    if existing:
        existing.total_value_cents = total_cents
        existing.total_cost_cents = cost_cents
        snapshot = existing
    else:
        snapshot = PortfolioSnapshot(
            date=on, total_value_cents=total_cents, total_cost_cents=cost_cents
        )
        session.add(snapshot)

    session.commit()
    return snapshot
