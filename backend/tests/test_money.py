"""Money must be exact. These tests exist to catch a regression to floats."""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.models import Holding, Security
from app.money import from_cents, parse_decimal, to_cents


@pytest.mark.parametrize(
    ("amount", "expected"),
    [
        ("0", 0),
        ("1", 100),
        ("12.34", 1234),
        ("-45.67", -4567),
        ("0.1", 10),
        # Half-up, the convention people expect from money. Python's default
        # banker's rounding would make this 0 and 2 respectively.
        ("0.005", 1),
        ("2.345", 235),
    ],
)
def test_to_cents_rounds_half_up(amount: str, expected: int) -> None:
    assert to_cents(Decimal(amount)) == expected


def test_round_trip_preserves_value() -> None:
    for cents in (0, 1, -1, 99, 100, 123456, -987654):
        assert to_cents(from_cents(cents)) == cents


def test_summing_many_amounts_has_no_drift() -> None:
    """0.1 + 0.2 != 0.3 in binary float; in integer cents it is exact."""
    cents = [to_cents(Decimal("0.1")) for _ in range(1000)]
    assert sum(cents) == 10_000
    assert from_cents(sum(cents)) == Decimal("100.00")


def test_quantize_price_removes_float_artifacts() -> None:
    """What yfinance actually hands us for a €309.38 stock."""
    from app.money import quantize_price

    assert quantize_price(parse_decimal(309.3800048828125)) == Decimal("309.38")
    assert quantize_price(parse_decimal(172.1199951171875)) == Decimal("172.12")


def test_quantize_price_never_uses_scientific_notation() -> None:
    """`normalize()` alone would turn 1200 into 1.2E+3 and reach the UI."""
    from app.money import quantize_price

    assert str(quantize_price(Decimal("1200.0000"))) == "1200"
    assert str(quantize_price(Decimal("100000"))) == "100000"
    # Genuine sub-cent precision survives.
    assert str(quantize_price(Decimal("0.0525"))) == "0.0525"


def test_parse_decimal_avoids_binary_float_artifacts() -> None:
    # Decimal(0.1) would be 0.1000000000000000055511151231257827...
    assert parse_decimal(0.1) == Decimal("0.1")
    assert parse_decimal("2.675") == Decimal("2.675")


def test_exact_decimal_column_round_trips(session: Session) -> None:
    """Fractional share quantities must survive a DB round trip exactly."""
    security = Security(ticker="TEST", name="Test", currency="EUR")
    session.add(security)
    session.flush()

    quantity = Decimal("1.23456789")
    session.add(Holding(security_id=security.id, quantity=quantity))
    session.commit()
    session.expunge_all()

    loaded = session.query(Holding).one()
    assert loaded.quantity == quantity
    assert str(loaded.quantity) == "1.23456789"
