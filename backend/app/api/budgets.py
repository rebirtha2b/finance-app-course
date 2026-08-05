"""Budget CRUD and status."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db import get_session
from app.models import Budget, Category, CategoryKind
from app.money import from_cents, to_cents
from app.schemas.budget import (
    BudgetCreate,
    BudgetOut,
    BudgetStatusOut,
    BudgetStatusSummary,
    BudgetUpdate,
)
from app.services.budgets import BudgetStatus, all_statuses

router = APIRouter(prefix="/api/budgets", tags=["budgets"])


def to_out(budget: Budget) -> BudgetOut:
    return BudgetOut(
        id=budget.id,
        category_id=budget.category_id,
        period=budget.period,
        limit=from_cents(budget.limit_cents),
        start_month=budget.start_month,
        rollover=budget.rollover,
        active=budget.active,
        category_name=budget.category.name if budget.category else None,
    )


def status_to_out(s: BudgetStatus) -> BudgetStatusOut:
    return BudgetStatusOut(
        budget_id=s.budget_id,
        category_id=s.category_id,
        category_name=s.category_name,
        period=s.period,
        limit=from_cents(s.limit_cents),
        effective_limit=from_cents(s.effective_limit_cents),
        spent=from_cents(s.spent_cents),
        remaining=from_cents(s.remaining_cents),
        rollover=from_cents(s.rollover_cents),
        percent_used=s.percent_used,
        over_budget=s.over_budget,
        window_start=s.window_start,
        window_end=s.window_end,
    )


@router.get("", response_model=list[BudgetOut])
def list_budgets(
    include_inactive: bool = True, session: Session = Depends(get_session)
) -> list[BudgetOut]:
    stmt = select(Budget).options(selectinload(Budget.category))
    if not include_inactive:
        stmt = stmt.where(Budget.active)
    return [to_out(b) for b in session.scalars(stmt)]


@router.get("/status", response_model=BudgetStatusSummary)
def budget_status(
    month: date | None = Query(
        default=None, description="Any date in the month of interest; defaults to today"
    ),
    session: Session = Depends(get_session),
) -> BudgetStatusSummary:
    month = month or date.today()
    statuses = all_statuses(session, month)
    items = [status_to_out(s) for s in statuses]

    return BudgetStatusSummary(
        month=month.replace(day=1),
        items=items,
        total_limit=from_cents(sum(s.effective_limit_cents for s in statuses)),
        total_spent=from_cents(sum(s.spent_cents for s in statuses)),
        total_remaining=from_cents(sum(s.remaining_cents for s in statuses)),
    )


@router.post("", response_model=BudgetOut, status_code=status.HTTP_201_CREATED)
def create_budget(
    payload: BudgetCreate, session: Session = Depends(get_session)
) -> BudgetOut:
    category = session.get(Category, payload.category_id)
    if category is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Category not found")
    if category.kind != CategoryKind.expense:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "Budgets apply to expense categories only.",
        )

    existing = session.scalar(
        select(Budget).where(
            Budget.category_id == payload.category_id, Budget.period == payload.period
        )
    )
    if existing:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "This category already has a budget for that period; edit it instead.",
        )

    budget = Budget(
        category_id=payload.category_id,
        period=payload.period,
        limit_cents=to_cents(payload.limit),
        start_month=payload.start_month or date.today().replace(day=1),
        rollover=payload.rollover,
    )
    session.add(budget)
    session.commit()
    session.refresh(budget)
    return to_out(budget)


def _get_or_404(session: Session, budget_id: int) -> Budget:
    budget = session.get(Budget, budget_id)
    if budget is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Budget not found")
    return budget


@router.patch("/{budget_id}", response_model=BudgetOut)
def update_budget(
    budget_id: int, payload: BudgetUpdate, session: Session = Depends(get_session)
) -> BudgetOut:
    budget = _get_or_404(session, budget_id)
    data = payload.model_dump(exclude_unset=True)
    if "limit" in data:
        budget.limit_cents = to_cents(data.pop("limit"))
    for field, value in data.items():
        setattr(budget, field, value)
    session.commit()
    session.refresh(budget)
    return to_out(budget)


@router.delete("/{budget_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_budget(budget_id: int, session: Session = Depends(get_session)) -> None:
    # A budget holds no history of its own — deleting it loses nothing.
    session.delete(_get_or_404(session, budget_id))
    session.commit()
