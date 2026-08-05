"""Recurring rule CRUD, manual generation, and the subscriptions view."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db import get_session
from app.models import Account, Category, CategoryKind, RecurringRule, Transaction
from app.money import from_cents, to_cents
from app.schemas.recurring import (
    GenerationOut,
    RecurringRuleCreate,
    RecurringRuleOut,
    RecurringRuleUpdate,
    SubscriptionsSummary,
)
from app.services.recurring import (
    generate_due_transactions,
    monthly_equivalent_cents,
    next_due_date,
)

router = APIRouter(prefix="/api", tags=["recurring"])


def to_out(rule: RecurringRule) -> RecurringRuleOut:
    return RecurringRuleOut(
        id=rule.id,
        name=rule.name,
        amount=from_cents(rule.amount_cents),
        category_id=rule.category_id,
        account_id=rule.account_id,
        description=rule.description,
        frequency=rule.frequency,
        interval=rule.interval,
        day_of_month=rule.day_of_month,
        weekday=rule.weekday,
        start_date=rule.start_date,
        end_date=rule.end_date,
        active=rule.active,
        last_generated_date=rule.last_generated_date,
        category_name=rule.category.name if rule.category else None,
        account_name=rule.account.name if rule.account else None,
        monthly_equivalent=from_cents(monthly_equivalent_cents(rule)),
        next_due_date=next_due_date(rule),
    )


def _validate_refs(session: Session, account_id: int | None, category_id: int | None) -> None:
    if account_id is not None and session.get(Account, account_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Account not found")
    if category_id is not None and session.get(Category, category_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Category not found")


def _loaded(session: Session):
    return select(RecurringRule).options(
        selectinload(RecurringRule.category), selectinload(RecurringRule.account)
    )


@router.get("/recurring", response_model=list[RecurringRuleOut])
def list_rules(
    include_inactive: bool = True, session: Session = Depends(get_session)
) -> list[RecurringRuleOut]:
    stmt = _loaded(session).order_by(RecurringRule.name)
    if not include_inactive:
        stmt = stmt.where(RecurringRule.active)
    return [to_out(r) for r in session.scalars(stmt)]


@router.post(
    "/recurring", response_model=RecurringRuleOut, status_code=status.HTTP_201_CREATED
)
def create_rule(
    payload: RecurringRuleCreate, session: Session = Depends(get_session)
) -> RecurringRuleOut:
    _validate_refs(session, payload.account_id, payload.category_id)
    data = payload.model_dump()
    rule = RecurringRule(amount_cents=to_cents(data.pop("amount")), **data)
    session.add(rule)
    session.commit()
    session.refresh(rule)
    return to_out(rule)


def _get_or_404(session: Session, rule_id: int) -> RecurringRule:
    rule = session.get(RecurringRule, rule_id)
    if rule is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Recurring rule not found")
    return rule


@router.patch("/recurring/{rule_id}", response_model=RecurringRuleOut)
def update_rule(
    rule_id: int, payload: RecurringRuleUpdate, session: Session = Depends(get_session)
) -> RecurringRuleOut:
    rule = _get_or_404(session, rule_id)
    data = payload.model_dump(exclude_unset=True)
    _validate_refs(session, data.get("account_id"), data.get("category_id"))

    if "amount" in data:
        # Only future generations use the new amount; already-generated
        # transactions keep the figure that was actually charged.
        rule.amount_cents = to_cents(data.pop("amount"))
    for field, value in data.items():
        setattr(rule, field, value)

    if rule.end_date and rule.end_date < rule.start_date:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "End date must not be before the start date",
        )

    session.commit()
    session.refresh(rule)
    return to_out(rule)


@router.delete("/recurring/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_rule(
    rule_id: int,
    delete_transactions: bool = False,
    session: Session = Depends(get_session),
) -> None:
    """Delete a rule.

    By default the transactions it already generated are kept — they record
    money that genuinely moved. `delete_transactions=true` removes them too,
    for a rule created by mistake.
    """
    rule = _get_or_404(session, rule_id)

    if delete_transactions:
        for txn in session.scalars(
            select(Transaction).where(Transaction.recurring_rule_id == rule_id)
        ):
            session.delete(txn)
    # Otherwise the FK is ON DELETE SET NULL, so history survives detached
    # from the rule.

    session.delete(rule)
    session.commit()


@router.post("/recurring/generate", response_model=GenerationOut)
def generate(
    until: date | None = None, session: Session = Depends(get_session)
) -> GenerationOut:
    """Materialize due transactions now. Safe to call repeatedly."""
    result = generate_due_transactions(session, until=until)
    return GenerationOut(created=result.created, rules_processed=result.rules_processed)


@router.get("/subscriptions", response_model=SubscriptionsSummary)
def subscriptions(session: Session = Depends(get_session)) -> SubscriptionsSummary:
    """Active recurring *expenses*, with each cost normalised to per-month.

    Income rules are excluded: this view answers "what are my committed
    outgoings", which is the number worth staring at.
    """
    rules = [
        r
        for r in session.scalars(_loaded(session).where(RecurringRule.active))
        if r.category and r.category.kind == CategoryKind.expense
    ]

    items = [to_out(r) for r in rules]
    items.sort(key=lambda i: i.monthly_equivalent or 0, reverse=True)

    total_monthly_cents = sum(monthly_equivalent_cents(r) for r in rules)
    return SubscriptionsSummary(
        items=items,
        total_monthly=from_cents(total_monthly_cents),
        total_annual=from_cents(total_monthly_cents * 12),
    )
