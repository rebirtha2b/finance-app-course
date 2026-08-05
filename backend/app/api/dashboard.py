"""One endpoint returning everything above the fold on the landing page."""

from __future__ import annotations

from datetime import date as DateType
from decimal import Decimal

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_session
from app.money import from_cents
from app.schemas.budget import BudgetStatusOut
from app.services import analytics
from app.services.budgets import all_statuses
from app.services.portfolio import value_portfolio
from app.api.budgets import status_to_out

router = APIRouter(prefix="/api", tags=["dashboard"])


class MonthFlowOut(BaseModel):
    month: DateType
    income: Decimal
    expenses: Decimal
    net: Decimal


class CategorySpendOut(BaseModel):
    category_id: int
    name: str
    color: str | None
    amount: Decimal
    percent: float


class UpcomingChargeOut(BaseModel):
    rule_id: int
    name: str
    amount: Decimal
    due_date: DateType
    days_away: int
    category_name: str | None


class PortfolioCardOut(BaseModel):
    total_value: Decimal
    day_change: Decimal
    total_gain: Decimal | None
    total_gain_percent: float | None
    holdings_count: int
    has_stale_prices: bool
    prices_as_of: DateType | None


class DashboardOut(BaseModel):
    base_currency: str
    today: DateType
    # Cash across all accounts plus the portfolio's market value.
    net_worth: Decimal
    cash_total: Decimal
    this_month: MonthFlowOut
    cash_flow: list[MonthFlowOut]
    spending_by_category: list[CategorySpendOut]
    budgets_at_risk: list[BudgetStatusOut]
    portfolio: PortfolioCardOut
    upcoming: list[UpcomingChargeOut]


@router.get("/dashboard", response_model=DashboardOut)
def dashboard(session: Session = Depends(get_session)) -> DashboardOut:
    today = DateType.today()

    cash_cents = analytics.cash_total_cents(session)
    valuation = value_portfolio(session)

    statuses = all_statuses(session, today)
    # Only the ones worth reacting to: over budget, or close to it.
    at_risk = [s for s in statuses if s.over_budget or s.percent_used >= 75][:3]

    return DashboardOut(
        base_currency=settings.base_currency,
        today=today,
        net_worth=from_cents(cash_cents) + valuation.total_value_base,
        cash_total=from_cents(cash_cents),
        this_month=MonthFlowOut(**vars(analytics.month_flow(session, today))),
        cash_flow=[
            MonthFlowOut(**vars(m)) for m in analytics.cash_flow_series(session, 12, today)
        ],
        spending_by_category=[
            CategorySpendOut(**vars(c))
            for c in analytics.spending_by_category(session, today)
        ],
        budgets_at_risk=[status_to_out(s) for s in at_risk],
        portfolio=PortfolioCardOut(
            total_value=valuation.total_value_base,
            day_change=valuation.day_change_base,
            total_gain=valuation.total_gain_base,
            total_gain_percent=valuation.total_gain_percent,
            holdings_count=len(valuation.holdings),
            has_stale_prices=valuation.has_stale_prices,
            prices_as_of=valuation.prices_as_of,
        ),
        upcoming=[
            UpcomingChargeOut(**vars(c)) for c in analytics.upcoming_charges(session)
        ],
    )
