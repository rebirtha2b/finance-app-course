"""Portfolio valuation, FX conversion, and — most importantly — what happens
when the price source fails."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.models import Holding, Security
from app.services import fx
from app.services.portfolio import (
    latest_price,
    record_snapshot,
    refresh_prices,
    store_price,
    value_portfolio,
)


def add_holding(
    session: Session,
    ticker: str,
    quantity: str,
    *,
    currency: str = "USD",
    avg_cost: str | None = None,
) -> Holding:
    security = Security(ticker=ticker, name=f"{ticker} Inc", currency=currency)
    session.add(security)
    session.flush()
    holding = Holding(
        security_id=security.id,
        quantity=Decimal(quantity),
        avg_cost_price=Decimal(avg_cost) if avg_cost else None,
    )
    session.add(holding)
    session.commit()
    return holding


# ------------------------------------------------------------- basic maths


def test_values_a_eur_holding(session: Session, fake_prices) -> None:
    add_holding(session, "SAP.DE", "10", currency="EUR")
    fake_prices.add_security("SAP.DE", currency="EUR", price="167.38")

    refresh_prices(session)
    v = value_portfolio(session)

    assert len(v.holdings) == 1
    row = v.holdings[0]
    assert row.price == Decimal("167.38")
    assert row.value_native == Decimal("1673.80")
    # No conversion needed; base currency is EUR.
    assert row.value_base == Decimal("1673.80")
    assert v.total_value_base == Decimal("1673.80")


def test_converts_usd_holding_at_known_rate(session: Session, fake_prices) -> None:
    """10 AAPL at $200 with EUR/USD 1.25 must be exactly €1600."""
    add_holding(session, "AAPL", "10", currency="USD")
    fake_prices.add_security("AAPL", currency="USD", price="200.00")
    fake_prices.set_fx("EUR", "USD", "1.25")

    refresh_prices(session)
    v = value_portfolio(session)

    row = v.holdings[0]
    assert row.value_native == Decimal("2000.00")
    # $2000 / 1.25 = €1600
    assert row.value_base == Decimal("1600.00")


def test_fractional_shares_are_exact(session: Session, fake_prices) -> None:
    add_holding(session, "VWCE.DE", "1.23456789", currency="EUR")
    fake_prices.add_security("VWCE.DE", currency="EUR", price="100.00")

    refresh_prices(session)
    v = value_portfolio(session)

    # The quantity keeps full precision...
    assert v.holdings[0].quantity == Decimal("1.23456789")
    # ...while the resulting monetary value is rounded to cents, because
    # 123.456789 euros is not a thing you can hold.
    assert v.holdings[0].value_base == Decimal("123.46")


def test_gain_loss_against_average_cost(session: Session, fake_prices) -> None:
    add_holding(session, "SAP.DE", "10", currency="EUR", avg_cost="100.00")
    fake_prices.add_security("SAP.DE", currency="EUR", price="150.00")

    refresh_prices(session)
    row = value_portfolio(session).holdings[0]

    assert row.cost_basis_base == Decimal("1000.00")
    assert row.gain_base == Decimal("500.00")
    assert row.gain_percent == pytest.approx(50.0)


def test_loss_is_negative(session: Session, fake_prices) -> None:
    add_holding(session, "SAP.DE", "10", currency="EUR", avg_cost="200.00")
    fake_prices.add_security("SAP.DE", currency="EUR", price="150.00")

    refresh_prices(session)
    row = value_portfolio(session).holdings[0]

    assert row.gain_base == Decimal("-500.00")
    assert row.gain_percent == pytest.approx(-25.0)


def test_holding_without_cost_has_no_gain(session: Session, fake_prices) -> None:
    add_holding(session, "SAP.DE", "10", currency="EUR")
    fake_prices.add_security("SAP.DE", currency="EUR", price="150.00")

    refresh_prices(session)
    v = value_portfolio(session)

    assert v.holdings[0].gain_base is None
    assert v.total_cost_base is None
    assert v.total_gain_base is None


def test_total_gain_ignores_holdings_without_a_cost_basis(
    session: Session, fake_prices
) -> None:
    """Regression: the total gain must not compare all holdings' value against
    only the costed holdings' cost.

    WITH_COST doubled (cost €1000 -> value €2000, +€1000). NO_COST is worth
    €5000 but has no cost recorded, so it contributes nothing to gain.
    Subtracting total_cost from total_value would report €6000 of "gain".
    """
    add_holding(session, "WITH_COST", "10", currency="EUR", avg_cost="100.00")
    add_holding(session, "NO_COST", "10", currency="EUR")
    fake_prices.add_security("WITH_COST", currency="EUR", price="200.00")
    fake_prices.add_security("NO_COST", currency="EUR", price="500.00")

    refresh_prices(session)
    v = value_portfolio(session)

    assert v.total_value_base == Decimal("7000.00")
    assert v.total_cost_base == Decimal("1000.00")
    assert v.total_gain_base == Decimal("1000.00")
    assert v.total_gain_percent == pytest.approx(100.0)


def test_allocation_percentages_sum_to_100(session: Session, fake_prices) -> None:
    add_holding(session, "A", "10", currency="EUR")
    add_holding(session, "B", "30", currency="EUR")
    fake_prices.add_security("A", currency="EUR", price="10.00")  # 100
    fake_prices.add_security("B", currency="EUR", price="10.00")  # 300

    refresh_prices(session)
    v = value_portfolio(session)

    allocations = {h.ticker: h.allocation_percent for h in v.holdings}
    assert allocations["A"] == pytest.approx(25.0)
    assert allocations["B"] == pytest.approx(75.0)
    assert sum(allocations.values()) == pytest.approx(100.0)


def test_day_change_uses_previous_close(session: Session, fake_prices) -> None:
    holding = add_holding(session, "SAP.DE", "10", currency="EUR")
    security = session.get(Security, holding.security_id)

    store_price(session, security, Decimal("100.00"), date(2026, 8, 3), "EUR")
    store_price(session, security, Decimal("110.00"), date(2026, 8, 4), "EUR")
    session.commit()

    row = value_portfolio(session, on=date(2026, 8, 4)).holdings[0]
    assert row.day_change_base == Decimal("100.00")  # 10 shares x €10
    assert row.day_change_percent == pytest.approx(10.0)


# ------------------------------------------------- failure modes (the point)


def test_total_outage_keeps_last_known_price(session: Session, fake_prices) -> None:
    """The core promise: a failed fetch never shows €0."""
    add_holding(session, "SAP.DE", "10", currency="EUR")
    fake_prices.add_security("SAP.DE", currency="EUR", price="150.00")
    refresh_prices(session)
    assert value_portfolio(session).total_value_base == Decimal("1500.00")

    # Upstream now fails completely.
    fake_prices.raise_on_calls = True
    result = refresh_prices(session)

    assert result.prices_updated == 0
    v = value_portfolio(session)
    assert v.total_value_base == Decimal("1500.00")  # not zero
    assert v.holdings[0].price == Decimal("150.00")


def test_partial_failure_keeps_the_good_data(session: Session, fake_prices) -> None:
    add_holding(session, "GOOD", "10", currency="EUR")
    add_holding(session, "BAD", "10", currency="EUR")
    fake_prices.add_security("GOOD", currency="EUR", price="100.00")
    fake_prices.add_security("BAD", currency="EUR", price="50.00")
    refresh_prices(session)

    # BAD stops returning data; GOOD moves.
    fake_prices.omit = {"BAD"}
    fake_prices.set_price("GOOD", "120.00", date(2026, 8, 5), "EUR")
    result = refresh_prices(session)

    assert result.prices_updated == 1
    assert result.failed_tickers == ["BAD"]
    assert result.ok is False

    values = {h.ticker: h.value_base for h in value_portfolio(session).holdings}
    assert values["GOOD"] == Decimal("1200.00")  # updated
    assert values["BAD"] == Decimal("500.00")  # last known, not zero


def test_stale_flag_marks_the_older_price(session: Session, fake_prices) -> None:
    add_holding(session, "FRESH", "1", currency="EUR")
    add_holding(session, "OLD", "1", currency="EUR")
    fake_prices.add_security("FRESH", currency="EUR", price="10.00")
    fake_prices.add_security("OLD", currency="EUR", price="10.00")
    fake_prices.set_price("FRESH", "10.00", date(2026, 8, 5), "EUR")
    fake_prices.set_price("OLD", "10.00", date(2026, 8, 1), "EUR")

    refresh_prices(session)
    v = value_portfolio(session)

    by_ticker = {h.ticker: h for h in v.holdings}
    assert by_ticker["FRESH"].stale is False
    assert by_ticker["OLD"].stale is True
    assert v.has_stale_prices is True
    assert v.prices_as_of == date(2026, 8, 1)  # the oldest price in use


def test_never_priced_holding_is_shown_not_hidden(session: Session, fake_prices) -> None:
    """A holding we could never price must still be visible, with blanks."""
    add_holding(session, "UNKNOWN", "10", currency="EUR")

    refresh_prices(session)
    v = value_portfolio(session)

    assert len(v.holdings) == 1
    row = v.holdings[0]
    assert row.price is None
    assert row.value_base is None  # not Decimal(0)
    assert v.missing_prices == ["UNKNOWN"]
    assert v.has_stale_prices is True


def test_missing_fx_rate_does_not_invent_one(session: Session, fake_prices) -> None:
    """Without a rate we show no base value rather than pretending 1:1."""
    add_holding(session, "AAPL", "10", currency="USD")
    fake_prices.add_security("AAPL", currency="USD", price="200.00")
    # Deliberately no FX rate configured.

    refresh_prices(session)
    v = value_portfolio(session)

    row = v.holdings[0]
    assert row.value_native == Decimal("2000.00")
    assert row.value_base is None
    assert v.total_value_base == Decimal("0")


def test_zero_or_negative_price_is_rejected(session: Session, fake_prices) -> None:
    """A nonsense price is worse than no price — refuse to store it."""
    add_holding(session, "SAP.DE", "10", currency="EUR")
    fake_prices.add_security("SAP.DE", currency="EUR", price="150.00")
    refresh_prices(session)

    fake_prices.set_price("SAP.DE", "0", date(2026, 8, 5), "EUR")
    refresh_prices(session)

    assert value_portfolio(session).holdings[0].price == Decimal("150.00")


# ----------------------------------------------------------------- storage


def test_price_history_accumulates(session: Session, fake_prices) -> None:
    holding = add_holding(session, "SAP.DE", "10", currency="EUR")
    security = session.get(Security, holding.security_id)

    for day, price in [(3, "100"), (4, "110"), (5, "120")]:
        store_price(session, security, Decimal(price), date(2026, 8, day), "EUR")
    session.commit()

    assert latest_price(session, security.id).close_price == Decimal("120")
    # Valuation on a past date uses that date's price.
    assert latest_price(session, security.id, date(2026, 8, 4)).close_price == Decimal("110")


def test_refetching_same_day_updates_not_duplicates(session: Session, fake_prices) -> None:
    add_holding(session, "SAP.DE", "10", currency="EUR")
    fake_prices.add_security("SAP.DE", currency="EUR", price="100.00")

    refresh_prices(session)
    fake_prices.set_price("SAP.DE", "105.00", date(2026, 8, 4), "EUR")
    refresh_prices(session)

    from sqlalchemy import func, select

    from app.models import PriceSnapshot

    count = session.scalar(select(func.count()).select_from(PriceSnapshot))
    assert count == 1
    assert value_portfolio(session).holdings[0].price == Decimal("105.00")


def test_fx_inverse_pair_is_derived(session: Session) -> None:
    fx.store_rate(session, "EUR", "USD", Decimal("1.25"), date(2026, 8, 4))
    session.commit()

    assert fx.latest_rate(session, "EUR", "USD") == Decimal("1.25")
    # USD->EUR is derived rather than fetched separately.
    assert fx.latest_rate(session, "USD", "EUR") == Decimal("0.8")


def test_snapshot_records_totals(session: Session, fake_prices) -> None:
    add_holding(session, "SAP.DE", "10", currency="EUR", avg_cost="100.00")
    fake_prices.add_security("SAP.DE", currency="EUR", price="150.00")
    refresh_prices(session)

    snapshot = record_snapshot(session, on=date(2026, 8, 4))
    assert snapshot.total_value_cents == 150000
    assert snapshot.total_cost_cents == 100000

    # Same day again updates rather than duplicating.
    again = record_snapshot(session, on=date(2026, 8, 4))
    assert again.id == snapshot.id
