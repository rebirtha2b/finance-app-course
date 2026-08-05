"""Currency conversion against cached daily rates.

Rates are stored per (base, quote, date). Lookups take the most recent rate on
or before the date asked for, so a Saturday valuation uses Friday's rate
rather than failing.
"""

from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import FxRate, utcnow
from app.services.prices import get_provider

logger = logging.getLogger(__name__)


def store_rate(
    session: Session, base: str, quote: str, rate: Decimal, on: date | None = None
) -> FxRate:
    on = on or date.today()
    base, quote = base.upper(), quote.upper()

    existing = session.scalar(
        select(FxRate).where(
            FxRate.base == base, FxRate.quote == quote, FxRate.date == on
        )
    )
    if existing:
        existing.rate = rate
        existing.fetched_at = utcnow()
        return existing

    row = FxRate(
        base=base, quote=quote, date=on, rate=rate, fetched_at=utcnow()
    )
    session.add(row)
    return row


def latest_rate(
    session: Session, base: str, quote: str, on: date | None = None
) -> Decimal | None:
    """Most recent stored rate on or before `on`. None if we have never had one."""
    base, quote = base.upper(), quote.upper()
    if base == quote:
        return Decimal(1)

    stmt = select(FxRate).where(FxRate.base == base, FxRate.quote == quote)
    if on is not None:
        stmt = stmt.where(FxRate.date <= on)
    row = session.scalar(stmt.order_by(FxRate.date.desc()).limit(1))
    if row is not None:
        return row.rate

    # Try the inverse pair before giving up: storing EUR/USD gives us USD/EUR
    # for free, and halves the number of fetches.
    stmt = select(FxRate).where(FxRate.base == quote, FxRate.quote == base)
    if on is not None:
        stmt = stmt.where(FxRate.date <= on)
    row = session.scalar(stmt.order_by(FxRate.date.desc()).limit(1))
    if row is not None and row.rate != 0:
        return Decimal(1) / row.rate

    return None


def convert(
    amount: Decimal, rate: Decimal | None
) -> Decimal | None:
    return None if rate is None else amount * rate


def refresh_rates(session: Session, currencies: set[str], base: str) -> list[str]:
    """Fetch today's rate from `base` to each currency. Returns failed pairs.

    A failure is not fatal — `latest_rate` will keep serving the last known
    rate, which for FX is a far better approximation than nothing.
    """
    provider = get_provider()
    failures: list[str] = []

    for currency in sorted(currencies):
        if currency.upper() == base.upper():
            continue
        try:
            rate = provider.get_fx_rate(base, currency)
        except Exception:
            logger.exception("FX fetch raised for %s/%s", base, currency)
            rate = None

        if rate is None or rate <= 0:
            failures.append(f"{base}/{currency}")
            continue
        store_rate(session, base, currency, rate)

    return failures
