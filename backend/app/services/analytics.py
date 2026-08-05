"""Aggregations behind the dashboard.

Everything here reads from the same `Transaction` rows the transactions page
shows, so the dashboard can never disagree with the detail views — there is no
separate summary table to drift out of sync.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.models import Account, Category, RecurringRule, Transaction
from app.money import from_cents
from app.services.budgets import month_bounds, next_month
from app.services.recurring import next_due_date


@dataclass
class MonthFlow:
    month: date
    income: Decimal
    expenses: Decimal
    net: Decimal


@dataclass
class CategorySpend:
    category_id: int
    name: str
    color: str | None
    amount: Decimal
    percent: float


@dataclass
class UpcomingCharge:
    rule_id: int
    name: str
    amount: Decimal
    due_date: date
    days_away: int
    category_name: str | None


def account_balances_cents(session: Session) -> dict[int, int]:
    """Opening balance plus every transaction, per account."""
    sums = dict(
        session.execute(
            select(
                Transaction.account_id,
                func.coalesce(func.sum(Transaction.amount_cents), 0),
            ).group_by(Transaction.account_id)
        ).all()
    )
    return {
        account.id: account.opening_balance_cents + sums.get(account.id, 0)
        for account in session.scalars(select(Account))
    }


def cash_total_cents(session: Session) -> int:
    return sum(account_balances_cents(session).values())


def month_flow(session: Session, month: date) -> MonthFlow:
    start, end = month_bounds(month)
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

    return MonthFlow(
        month=start,
        income=from_cents(income),
        expenses=from_cents(abs(expenses)),
        net=from_cents(income + expenses),
    )


def cash_flow_series(session: Session, months: int = 12, until: date | None = None) -> list[MonthFlow]:
    """Income and expenses per month, oldest first.

    Months with no activity are included as zeros so the chart has an even
    time axis rather than silently collapsing gaps.
    """
    until = until or date.today()
    start = until.replace(day=1)
    for _ in range(months - 1):
        start = (start - timedelta(days=1)).replace(day=1)

    series: list[MonthFlow] = []
    cursor = start
    while cursor <= until.replace(day=1):
        series.append(month_flow(session, cursor))
        cursor = next_month(cursor)
    return series


def spending_by_category(
    session: Session, month: date, limit: int = 8
) -> list[CategorySpend]:
    """Current-month expenses grouped by *top-level* category.

    Children roll up into their parent: seeing "Food €420" is more useful at a
    glance than five separate grocery-shaped lines.
    """
    start, end = month_bounds(month)

    rows = session.execute(
        select(
            Category.id,
            Category.name,
            Category.color,
            Category.parent_id,
            func.sum(Transaction.amount_cents),
        )
        .join(Transaction, Transaction.category_id == Category.id)
        .where(
            Transaction.date >= start,
            Transaction.date <= end,
            Transaction.amount_cents < 0,
        )
        .group_by(Category.id)
    ).all()

    # Resolve each category to its top-level ancestor.
    parents = {
        c.id: c for c in session.scalars(select(Category).where(Category.parent_id.is_(None)))
    }
    totals: dict[int, int] = {}
    for cat_id, name, color, parent_id, total in rows:
        key = parent_id if parent_id is not None else cat_id
        totals[key] = totals.get(key, 0) + int(total)

    grand_total = sum(abs(v) for v in totals.values())
    result: list[CategorySpend] = []
    for cat_id, total_cents in totals.items():
        amount = abs(total_cents)
        parent = parents.get(cat_id)
        result.append(
            CategorySpend(
                category_id=cat_id,
                name=parent.name if parent else "Uncategorised",
                color=parent.color if parent else None,
                amount=from_cents(amount),
                percent=round(amount / grand_total * 100, 1) if grand_total else 0.0,
            )
        )

    result.sort(key=lambda c: c.amount, reverse=True)

    if len(result) > limit:
        rest = result[limit:]
        result = result[:limit]
        result.append(
            CategorySpend(
                category_id=-1,
                name="Other",
                color="#94a3b8",
                amount=sum((c.amount for c in rest), Decimal(0)),
                percent=round(sum(c.percent for c in rest), 1),
            )
        )

    return result


def upcoming_charges(
    session: Session, days: int = 14, today: date | None = None
) -> list[UpcomingCharge]:
    """Recurring charges falling due in the next `days` days."""
    today = today or date.today()
    horizon = today + timedelta(days=days)

    charges: list[UpcomingCharge] = []
    for rule in session.scalars(select(RecurringRule).where(RecurringRule.active)):
        # `after=today - 1 day` so something due *today* still counts as
        # upcoming rather than being skipped.
        due = next_due_date(rule, after=today - timedelta(days=1))
        if due is None or due > horizon:
            continue
        charges.append(
            UpcomingCharge(
                rule_id=rule.id,
                name=rule.name,
                amount=from_cents(rule.amount_cents),
                due_date=due,
                days_away=(due - today).days,
                category_name=rule.category.name if rule.category else None,
            )
        )

    charges.sort(key=lambda c: c.due_date)
    return charges
