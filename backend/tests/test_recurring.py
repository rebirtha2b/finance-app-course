"""The recurring generator is the one piece that writes money rows on its own.

Everything here guards against the two failure modes that would matter: a
double charge, or a date that quietly drifts.
"""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Account, Category, CategoryKind, Frequency, RecurringRule, Transaction
from app.services.recurring import (
    add_months,
    generate_due_transactions,
    monthly_equivalent_cents,
    next_due_date,
    occurrences,
)


@pytest.fixture()
def refs(session: Session) -> dict:
    account = Account(name="Main", currency="EUR")
    category = Category(name="Rent", kind=CategoryKind.expense)
    session.add_all([account, category])
    session.flush()
    return {"account_id": account.id, "category_id": category.id}


def make_rule(session: Session, refs: dict, **kwargs) -> RecurringRule:
    defaults = dict(
        name="Test rule",
        amount_cents=-1000_00,
        frequency=Frequency.monthly,
        interval=1,
        start_date=date(2026, 1, 1),
        account_id=refs["account_id"],
        category_id=refs["category_id"],
        description="Test",
    )
    rule = RecurringRule(**{**defaults, **kwargs})
    session.add(rule)
    session.flush()
    return rule


# ----------------------------------------------------------- date arithmetic


def test_add_months_clamps_to_month_length() -> None:
    assert add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)
    assert add_months(date(2026, 1, 31), 3) == date(2026, 4, 30)
    assert add_months(date(2026, 12, 31), 1) == date(2027, 1, 31)


def test_add_months_handles_leap_year() -> None:
    # 2028 is a leap year.
    assert add_months(date(2028, 1, 31), 1) == date(2028, 2, 29)


def test_monthly_on_31st_does_not_drift(session: Session, refs: dict) -> None:
    """The regression this whole design exists to prevent.

    February clamps to the 28th, but March must return to the 31st. Computing
    each date from the previous one would give March 28 and stay wrong forever.
    """
    rule = make_rule(session, refs, start_date=date(2026, 1, 31), day_of_month=31)
    dates = occurrences(rule, date(2026, 5, 31))
    assert dates == [
        date(2026, 1, 31),
        date(2026, 2, 28),
        date(2026, 3, 31),
        date(2026, 4, 30),
        date(2026, 5, 31),
    ]


def test_monthly_uses_day_of_month_over_start_day(session: Session, refs: dict) -> None:
    """Rule created on the 15th but billing on the 1st starts next month."""
    rule = make_rule(session, refs, start_date=date(2026, 1, 15), day_of_month=1)
    dates = occurrences(rule, date(2026, 4, 30))
    assert dates == [date(2026, 2, 1), date(2026, 3, 1), date(2026, 4, 1)]


def test_interval_greater_than_one(session: Session, refs: dict) -> None:
    rule = make_rule(session, refs, start_date=date(2026, 1, 10), interval=3)
    dates = occurrences(rule, date(2026, 12, 31))
    assert dates == [
        date(2026, 1, 10),
        date(2026, 4, 10),
        date(2026, 7, 10),
        date(2026, 10, 10),
    ]


def test_quarterly_and_yearly(session: Session, refs: dict) -> None:
    quarterly = make_rule(
        session, refs, frequency=Frequency.quarterly, start_date=date(2026, 1, 1)
    )
    assert occurrences(quarterly, date(2026, 12, 31)) == [
        date(2026, 1, 1),
        date(2026, 4, 1),
        date(2026, 7, 1),
        date(2026, 10, 1),
    ]

    yearly = make_rule(
        session, refs, frequency=Frequency.yearly, start_date=date(2026, 3, 5)
    )
    assert occurrences(yearly, date(2028, 12, 31)) == [
        date(2026, 3, 5),
        date(2027, 3, 5),
        date(2028, 3, 5),
    ]


def test_weekly_aligns_to_weekday(session: Session, refs: dict) -> None:
    # 2026-01-01 is a Thursday; weekday=0 is Monday, so the first occurrence
    # moves forward to Monday 2026-01-05.
    rule = make_rule(
        session,
        refs,
        frequency=Frequency.weekly,
        start_date=date(2026, 1, 1),
        weekday=0,
    )
    dates = occurrences(rule, date(2026, 1, 31))
    assert dates == [
        date(2026, 1, 5),
        date(2026, 1, 12),
        date(2026, 1, 19),
        date(2026, 1, 26),
    ]
    assert all(d.weekday() == 0 for d in dates)


def test_daily(session: Session, refs: dict) -> None:
    rule = make_rule(
        session, refs, frequency=Frequency.daily, start_date=date(2026, 1, 1)
    )
    assert occurrences(rule, date(2026, 1, 5)) == [
        date(2026, 1, 1),
        date(2026, 1, 2),
        date(2026, 1, 3),
        date(2026, 1, 4),
        date(2026, 1, 5),
    ]


def test_end_date_truncates_series(session: Session, refs: dict) -> None:
    rule = make_rule(
        session, refs, start_date=date(2026, 1, 1), end_date=date(2026, 3, 15)
    )
    assert occurrences(rule, date(2026, 12, 31)) == [
        date(2026, 1, 1),
        date(2026, 2, 1),
        date(2026, 3, 1),
    ]


def test_no_occurrences_before_start(session: Session, refs: dict) -> None:
    rule = make_rule(session, refs, start_date=date(2026, 6, 1))
    assert occurrences(rule, date(2026, 1, 1)) == []


# -------------------------------------------------------------- generation


def test_catch_up_from_past_start(session: Session, refs: dict) -> None:
    """A rule starting three months ago produces exactly three transactions."""
    make_rule(session, refs, start_date=date(2026, 5, 1))
    result = generate_due_transactions(session, until=date(2026, 7, 15))

    assert result.created == 3
    dates = list(session.scalars(select(Transaction.date).order_by(Transaction.date)))
    assert dates == [date(2026, 5, 1), date(2026, 6, 1), date(2026, 7, 1)]


def test_generation_is_idempotent(session: Session, refs: dict) -> None:
    """Startup + daily job means this runs repeatedly; it must not duplicate."""
    make_rule(session, refs, start_date=date(2026, 5, 1))

    first = generate_due_transactions(session, until=date(2026, 7, 15))
    second = generate_due_transactions(session, until=date(2026, 7, 15))
    third = generate_due_transactions(session, until=date(2026, 7, 15))

    assert first.created == 3
    assert second.created == 0
    assert third.created == 0
    assert session.scalar(select(func.count()).select_from(Transaction)) == 3


def test_generation_extends_incrementally(session: Session, refs: dict) -> None:
    make_rule(session, refs, start_date=date(2026, 5, 1))

    generate_due_transactions(session, until=date(2026, 6, 15))
    assert session.scalar(select(func.count()).select_from(Transaction)) == 2

    generate_due_transactions(session, until=date(2026, 8, 15))
    assert session.scalar(select(func.count()).select_from(Transaction)) == 4


def test_paused_rule_generates_nothing(session: Session, refs: dict) -> None:
    make_rule(session, refs, start_date=date(2026, 5, 1), active=False)
    assert generate_due_transactions(session, until=date(2026, 8, 1)).created == 0


def test_editing_a_generated_transaction_survives_regeneration(
    session: Session, refs: dict
) -> None:
    """Rent went up for one month; the edit must not be reverted or duplicated."""
    make_rule(session, refs, start_date=date(2026, 5, 1))
    generate_due_transactions(session, until=date(2026, 7, 15))

    june = session.scalar(select(Transaction).where(Transaction.date == date(2026, 6, 1)))
    june.amount_cents = -1100_00
    june.description = "Rent (increased)"
    session.commit()

    generate_due_transactions(session, until=date(2026, 7, 15))

    reloaded = session.scalar(
        select(Transaction).where(Transaction.due_date == date(2026, 6, 1))
    )
    assert reloaded.amount_cents == -1100_00
    assert reloaded.description == "Rent (increased)"
    assert session.scalar(select(func.count()).select_from(Transaction)) == 3


def test_generated_transactions_carry_rule_metadata(session: Session, refs: dict) -> None:
    rule = make_rule(session, refs, start_date=date(2026, 5, 1), description="Flat rent")
    generate_due_transactions(session, until=date(2026, 5, 31))

    txn = session.scalar(select(Transaction))
    assert txn.recurring_rule_id == rule.id
    assert txn.due_date == date(2026, 5, 1)
    assert txn.description == "Flat rent"
    assert txn.amount_cents == -1000_00


def test_unique_constraint_backstops_double_insert(session: Session, refs: dict) -> None:
    """Even if the skip logic were bypassed, the DB refuses a second charge."""
    from sqlalchemy.exc import IntegrityError

    rule = make_rule(session, refs, start_date=date(2026, 5, 1))
    generate_due_transactions(session, until=date(2026, 5, 31))

    session.add(
        Transaction(
            date=date(2026, 5, 1),
            due_date=date(2026, 5, 1),
            amount_cents=-1000_00,
            account_id=refs["account_id"],
            category_id=refs["category_id"],
            description="Sneaky duplicate",
            recurring_rule_id=rule.id,
        )
    )
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


# ------------------------------------------------------- derived quantities


def test_next_due_date(session: Session, refs: dict) -> None:
    rule = make_rule(session, refs, start_date=date(2026, 1, 1))
    assert next_due_date(rule, after=date(2026, 3, 15)) == date(2026, 4, 1)
    # Exactly on a due date returns the following one, not today's.
    assert next_due_date(rule, after=date(2026, 4, 1)) == date(2026, 5, 1)


def test_next_due_date_none_after_end(session: Session, refs: dict) -> None:
    rule = make_rule(
        session, refs, start_date=date(2026, 1, 1), end_date=date(2026, 3, 1)
    )
    assert next_due_date(rule, after=date(2026, 6, 1)) is None


@pytest.mark.parametrize(
    ("frequency", "interval", "amount_cents", "expected"),
    [
        (Frequency.monthly, 1, -10_00, 1000),
        (Frequency.yearly, 1, -120_00, 1000),
        (Frequency.quarterly, 1, -30_00, 1000),
        (Frequency.weekly, 1, -10_00, round(1000 * 52 / 12)),
        (Frequency.monthly, 3, -30_00, 1000),  # every 3 months
    ],
)
def test_monthly_equivalent(
    session: Session, refs: dict, frequency, interval, amount_cents, expected
) -> None:
    rule = make_rule(
        session, refs, frequency=frequency, interval=interval, amount_cents=amount_cents
    )
    assert monthly_equivalent_cents(rule) == expected
