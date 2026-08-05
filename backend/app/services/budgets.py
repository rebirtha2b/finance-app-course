"""Budget status: what you set aside versus what you actually spent.

Two conventions worth stating up front, because they decide every number here:

* **Spending is stored negative**, so "spent" is the negation of the summed
  amounts. A refund lands as a positive amount and therefore *reduces* spend,
  which is the honest treatment — returning a €50 coat should give you €50 of
  your clothing budget back.
* **A budget on a parent category covers its children.** Budgeting "Food" and
  then spending on "Groceries" must count, or parent budgets would always read
  as zero.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Budget, BudgetPeriod, Category, Transaction


def month_bounds(month: date) -> tuple[date, date]:
    """First and last day of the calendar month containing `month`."""
    first = month.replace(day=1)
    last = first.replace(day=calendar.monthrange(first.year, first.month)[1])
    return first, last


def year_bounds(day: date) -> tuple[date, date]:
    return date(day.year, 1, 1), date(day.year, 12, 31)


def next_month(day: date) -> date:
    """The first day of the month after the one containing `day`."""
    if day.month == 12:
        return date(day.year + 1, 1, 1)
    return date(day.year, day.month + 1, 1)


def category_ids_for(session: Session, category_id: int) -> list[int]:
    child_ids = list(
        session.scalars(select(Category.id).where(Category.parent_id == category_id))
    )
    return [category_id, *child_ids]


def spend_cents(
    session: Session, category_ids: list[int], start: date, end: date
) -> int:
    """Net spend (positive number) for these categories in the window."""
    total = session.scalar(
        select(func.coalesce(func.sum(Transaction.amount_cents), 0)).where(
            Transaction.category_id.in_(category_ids),
            Transaction.date >= start,
            Transaction.date <= end,
        )
    )
    # Stored negative; report spend as a positive magnitude.
    return -(total or 0)


@dataclass
class BudgetStatus:
    budget_id: int
    category_id: int
    category_name: str
    period: BudgetPeriod
    limit_cents: int
    # Includes any rolled-over surplus; equals limit_cents when rollover is off.
    effective_limit_cents: int
    spent_cents: int
    remaining_cents: int
    rollover_cents: int
    percent_used: float
    over_budget: bool
    window_start: date
    window_end: date


def rollover_surplus_cents(
    session: Session, budget: Budget, category_ids: list[int], window_start: date
) -> int:
    """Unspent budget accumulated from `start_month` up to the current window.

    Only surpluses carry: an overspend in March does not silently shrink April's
    budget, which would make a bad month cascade into the rest of the year.
    """
    if not budget.rollover or budget.period != BudgetPeriod.monthly:
        return 0

    cursor = budget.start_month.replace(day=1)
    surplus = 0
    while cursor < window_start:
        start, end = month_bounds(cursor)
        spent = spend_cents(session, category_ids, start, end)
        surplus += max(0, budget.limit_cents - spent)
        cursor = next_month(cursor)
    return surplus


def status_for(session: Session, budget: Budget, month: date) -> BudgetStatus:
    if budget.period == BudgetPeriod.yearly:
        window_start, window_end = year_bounds(month)
    else:
        window_start, window_end = month_bounds(month)

    category_ids = category_ids_for(session, budget.category_id)
    spent = spend_cents(session, category_ids, window_start, window_end)

    rollover = rollover_surplus_cents(session, budget, category_ids, window_start)
    effective_limit = budget.limit_cents + rollover

    percent = (spent / effective_limit * 100) if effective_limit else 0.0

    return BudgetStatus(
        budget_id=budget.id,
        category_id=budget.category_id,
        category_name=budget.category.name if budget.category else "",
        period=budget.period,
        limit_cents=budget.limit_cents,
        effective_limit_cents=effective_limit,
        spent_cents=spent,
        remaining_cents=effective_limit - spent,
        rollover_cents=rollover,
        percent_used=round(percent, 1),
        # Strictly greater: spending exactly the limit is on budget, not over.
        over_budget=spent > effective_limit,
        window_start=window_start,
        window_end=window_end,
    )


def all_statuses(session: Session, month: date | None = None) -> list[BudgetStatus]:
    month = month or date.today()
    budgets = list(
        session.scalars(
            select(Budget).where(
                Budget.active, Budget.start_month <= month_bounds(month)[1]
            )
        )
    )
    statuses = [status_for(session, b, month) for b in budgets]
    # Most at risk first — that is the thing worth acting on.
    statuses.sort(key=lambda s: s.percent_used, reverse=True)
    return statuses
