"""Period-over-period comparisons and the yearly summary."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Category, Transaction
from app.money import from_cents
from app.services.budgets import month_bounds, year_bounds


@dataclass
class CategoryComparison:
    category_id: int
    name: str
    current: Decimal
    previous: Decimal
    change: Decimal
    # None when the previous period was zero — a percentage change from
    # nothing is undefined, not "infinity" or "100%".
    change_percent: float | None


@dataclass
class YearSummary:
    year: int
    income: Decimal
    expenses: Decimal
    net: Decimal
    # Share of income kept. None when there was no income, since dividing by
    # zero income would be meaningless.
    savings_rate: float | None
    months: list[dict]


def _spend_by_parent_category(
    session: Session, start: date, end: date
) -> dict[int, int]:
    """Expense totals (positive cents) keyed by top-level category id."""
    rows = session.execute(
        select(Category.id, Category.parent_id, func.sum(Transaction.amount_cents))
        .join(Transaction, Transaction.category_id == Category.id)
        .where(
            Transaction.date >= start,
            Transaction.date <= end,
            Transaction.amount_cents < 0,
        )
        .group_by(Category.id)
    ).all()

    totals: dict[int, int] = {}
    for cat_id, parent_id, total in rows:
        key = parent_id if parent_id is not None else cat_id
        totals[key] = totals.get(key, 0) + abs(int(total))
    return totals


def compare_periods(
    session: Session, current: tuple[date, date], previous: tuple[date, date]
) -> list[CategoryComparison]:
    now = _spend_by_parent_category(session, *current)
    before = _spend_by_parent_category(session, *previous)

    names = {
        c.id: c.name
        for c in session.scalars(
            select(Category).where(Category.id.in_(set(now) | set(before)))
        )
    }

    result = []
    for cat_id in set(now) | set(before):
        cur = now.get(cat_id, 0)
        prev = before.get(cat_id, 0)
        result.append(
            CategoryComparison(
                category_id=cat_id,
                name=names.get(cat_id, "Unknown"),
                current=from_cents(cur),
                previous=from_cents(prev),
                change=from_cents(cur - prev),
                change_percent=(
                    round((cur - prev) / prev * 100, 1) if prev else None
                ),
            )
        )

    # Biggest absolute swing first: that is what you want to look at.
    result.sort(key=lambda c: abs(c.change), reverse=True)
    return result


def month_over_month(session: Session, month: date) -> list[CategoryComparison]:
    current = month_bounds(month)
    prev_month_end = current[0].replace(day=1)
    prev_month_end = date(
        prev_month_end.year - 1 if prev_month_end.month == 1 else prev_month_end.year,
        12 if prev_month_end.month == 1 else prev_month_end.month - 1,
        1,
    )
    return compare_periods(session, current, month_bounds(prev_month_end))


def year_over_year(session: Session, year: int) -> list[CategoryComparison]:
    return compare_periods(
        session,
        (date(year, 1, 1), date(year, 12, 31)),
        (date(year - 1, 1, 1), date(year - 1, 12, 31)),
    )


def yearly_summary(session: Session, year: int) -> YearSummary:
    from sqlalchemy import case

    start, end = year_bounds(date(year, 1, 1))

    income, expenses = session.execute(
        select(
            func.coalesce(
                func.sum(
                    case((Transaction.amount_cents > 0, Transaction.amount_cents), else_=0)
                ),
                0,
            ),
            func.coalesce(
                func.sum(
                    case((Transaction.amount_cents < 0, Transaction.amount_cents), else_=0)
                ),
                0,
            ),
        ).where(Transaction.date >= start, Transaction.date <= end)
    ).one()

    months = []
    for m in range(1, 13):
        m_start, m_end = month_bounds(date(year, m, 1))
        m_income, m_expenses = session.execute(
            select(
                func.coalesce(
                    func.sum(
                        case(
                            (Transaction.amount_cents > 0, Transaction.amount_cents),
                            else_=0,
                        )
                    ),
                    0,
                ),
                func.coalesce(
                    func.sum(
                        case(
                            (Transaction.amount_cents < 0, Transaction.amount_cents),
                            else_=0,
                        )
                    ),
                    0,
                ),
            ).where(Transaction.date >= m_start, Transaction.date <= m_end)
        ).one()
        months.append(
            {
                "month": m_start.isoformat(),
                "income": str(from_cents(m_income)),
                "expenses": str(from_cents(abs(m_expenses))),
                "net": str(from_cents(m_income + m_expenses)),
            }
        )

    net = income + expenses
    return YearSummary(
        year=year,
        income=from_cents(income),
        expenses=from_cents(abs(expenses)),
        net=from_cents(net),
        savings_rate=round(net / income * 100, 1) if income else None,
        months=months,
    )
