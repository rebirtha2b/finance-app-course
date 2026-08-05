"""CSV round-tripping and the amount/date parsing that real bank exports need."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from app.services.csv_io import parse_amount, parse_date


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("12.34", Decimal("12.34")),
        ("-12.34", Decimal("-12.34")),
        # German format: dot thousands, comma decimals.
        ("1.234,56", Decimal("1234.56")),
        ("-1.234,56", Decimal("-1234.56")),
        # English format: comma thousands, dot decimals.
        ("1,234.56", Decimal("1234.56")),
        # Lone comma as decimal separator.
        ("12,34", Decimal("12.34")),
        # Lone comma as a thousands separator (3 digits after).
        ("1,234", Decimal("1234")),
        ("€ 45,00", Decimal("45.00")),
        ("$1,000.00", Decimal("1000.00")),
        # Trailing minus, as some exports emit.
        ("123.45-", Decimal("-123.45")),
        ("", None),
        ("not a number", None),
    ],
)
def test_parse_amount_handles_bank_formats(raw: str, expected) -> None:
    assert parse_amount(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("2026-08-05", date(2026, 8, 5)),
        ("05.08.2026", date(2026, 8, 5)),
        ("05/08/2026", date(2026, 8, 5)),
        ("2026/08/05", date(2026, 8, 5)),
        ("not a date", None),
        ("", None),
    ],
)
def test_parse_date_handles_common_formats(raw: str, expected) -> None:
    assert parse_date(raw) == expected


def test_ambiguous_thousands_vs_decimal_prefers_decimal_for_two_digits() -> None:
    """"12,34" is 12.34 (decimal), "1,234" is 1234 (thousands).

    The rule is the digit count after the separator — the only signal
    available without knowing the source locale.
    """
    assert parse_amount("12,34") == Decimal("12.34")
    assert parse_amount("1,234") == Decimal("1234")
