"""Money and exact-decimal handling.

Rule for the whole codebase: monetary amounts are integer minor units (cents)
in the database and `Decimal` in Python. Never `float`. Summing floats
accumulates representation error, which shows up as totals that disagree by a
cent between two screens that are supposedly showing the same number.

Share quantities and unit prices need more than 2 decimal places (fractional
shares, 4-dp quotes), so those use `ExactDecimal`, which stores the decimal as
text and round-trips it exactly. SQLAlchemy's `Numeric` on SQLite goes through
a float internally, so it is not safe for this.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from sqlalchemy import String, TypeDecorator

CENTS = Decimal("0.01")


def to_cents(amount: Decimal | int | str) -> int:
    """Convert a currency amount to integer cents, rounding half-up.

    Half-up is the convention people expect from money (0.005 -> 0.01);
    Python's default banker's rounding would give 0.00 here.
    """
    if not isinstance(amount, Decimal):
        amount = Decimal(str(amount))
    return int(amount.quantize(CENTS, rounding=ROUND_HALF_UP) * 100)


def from_cents(cents: int) -> Decimal:
    """Convert integer cents back to a 2-decimal-place `Decimal`."""
    return (Decimal(cents) / 100).quantize(CENTS)


def parse_decimal(value: Decimal | int | float | str) -> Decimal:
    """Coerce user input to `Decimal` without going through binary float.

    Floats are stringified first: `Decimal(0.1)` is 0.1000000000000000055...,
    while `Decimal(str(0.1))` is exactly 0.1.
    """
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError(f"Not a valid decimal: {value!r}") from exc


PRICE_PRECISION = Decimal("0.0001")


def quantize_money(value: Decimal) -> Decimal:
    """Round a computed monetary value to 2 dp for display."""
    return value.quantize(CENTS, rounding=ROUND_HALF_UP)


def quantize_price(value: Decimal) -> Decimal:
    """Round a quoted price to 4 dp and drop meaningless trailing zeros.

    Upstream prices arrive as floats, so `str()` on them exposes the binary
    representation: 309.3800048828125 for what is really 309.38. Four decimal
    places is the widest precision equities actually quote at, and it discards
    the float noise entirely.
    """
    rounded = value.quantize(PRICE_PRECISION, rounding=ROUND_HALF_UP)
    trimmed = rounded.normalize()
    # `normalize()` turns 1200.0000 into 1.2E+3, which would reach the UI as
    # scientific notation. Re-quantizing whole numbers restores plain digits.
    if trimmed == trimmed.to_integral_value():
        return trimmed.quantize(Decimal(1))
    return trimmed


class ExactDecimal(TypeDecorator):
    """A `Decimal` column stored as text, preserving exact value and scale."""

    impl = String
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        return str(parse_decimal(value))

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return Decimal(value)
