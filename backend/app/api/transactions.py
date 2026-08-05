"""Transaction CRUD and the filtered list that drives the main table."""

from __future__ import annotations

from datetime import date as Date
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import Select, case, func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.db import get_session
from app.models import Account, Category, Transaction
from app.money import from_cents, to_cents
from app.schemas.common import TransactionPage, TransactionTotals
from app.schemas.core import TransactionCreate, TransactionOut, TransactionUpdate

router = APIRouter(prefix="/api/transactions", tags=["transactions"])

SortField = Literal["date", "amount", "description"]


def to_out(txn: Transaction) -> TransactionOut:
    return TransactionOut(
        id=txn.id,
        date=txn.date,
        amount=from_cents(txn.amount_cents),
        account_id=txn.account_id,
        category_id=txn.category_id,
        description=txn.description,
        notes=txn.notes,
        recurring_rule_id=txn.recurring_rule_id,
        due_date=txn.due_date,
        category_name=txn.category.name if txn.category else None,
        category_kind=txn.category.kind if txn.category else None,
        account_name=txn.account.name if txn.account else None,
    )


def _validate_refs(session: Session, account_id: int | None, category_id: int | None) -> None:
    if account_id is not None and session.get(Account, account_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Account not found")
    if category_id is not None and session.get(Category, category_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Category not found")


def _category_ids(session: Session, category_id: int) -> list[int]:
    """A category filter includes its children.

    Filtering on "Food" should show Groceries and Restaurants too — otherwise
    selecting a parent category appears to return nothing.
    """
    child_ids = list(
        session.scalars(select(Category.id).where(Category.parent_id == category_id))
    )
    return [category_id, *child_ids]


def _apply_filters(
    stmt: Select,
    session: Session,
    date_from: Date | None,
    date_to: Date | None,
    category_id: int | None,
    account_id: int | None,
    q: str | None,
) -> Select:
    if date_from is not None:
        stmt = stmt.where(Transaction.date >= date_from)
    if date_to is not None:
        stmt = stmt.where(Transaction.date <= date_to)
    if category_id is not None:
        stmt = stmt.where(Transaction.category_id.in_(_category_ids(session, category_id)))
    if account_id is not None:
        stmt = stmt.where(Transaction.account_id == account_id)
    if q:
        pattern = f"%{q}%"
        stmt = stmt.where(
            or_(Transaction.description.ilike(pattern), Transaction.notes.ilike(pattern))
        )
    return stmt


@router.get("", response_model=TransactionPage[TransactionOut])
def list_transactions(
    date_from: Date | None = Query(default=None, alias="from"),
    date_to: Date | None = Query(default=None, alias="to"),
    category_id: int | None = None,
    account_id: int | None = None,
    q: str | None = None,
    sort: SortField = "date",
    order: Literal["asc", "desc"] = "desc",
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_session),
) -> TransactionPage[TransactionOut]:
    base = _apply_filters(
        select(Transaction), session, date_from, date_to, category_id, account_id, q
    )

    # Count and totals reuse `base`'s WHERE clause via with_only_columns, so
    # the numbers can never drift from the rows the filter actually matches.
    total = session.scalar(base.with_only_columns(func.count(Transaction.id)))

    # Totals cover the whole filtered set, not just the visible page — a page
    # total would be a misleading number to put next to a filter.
    income, expenses = session.execute(
        base.with_only_columns(
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
        )
    ).one()

    sort_column = {
        "date": Transaction.date,
        "amount": Transaction.amount_cents,
        "description": Transaction.description,
    }[sort]
    ordering = sort_column.desc() if order == "desc" else sort_column.asc()

    stmt = (
        base.options(
            selectinload(Transaction.category), selectinload(Transaction.account)
        )
        # id as a tiebreaker keeps pagination stable when many rows share a date.
        .order_by(ordering, Transaction.id.desc())
        .limit(limit)
        .offset(offset)
    )
    items = [to_out(t) for t in session.scalars(stmt)]

    return TransactionPage[TransactionOut](
        items=items,
        total=total or 0,
        limit=limit,
        offset=offset,
        totals=TransactionTotals(
            income=from_cents(income or 0),
            expenses=from_cents(abs(expenses or 0)),
            net=from_cents((income or 0) + (expenses or 0)),
        ),
    )


def _get_or_404(session: Session, txn_id: int) -> Transaction:
    txn = session.get(Transaction, txn_id)
    if txn is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Transaction not found")
    return txn


@router.get("/{txn_id}", response_model=TransactionOut)
def get_transaction(
    txn_id: int, session: Session = Depends(get_session)
) -> TransactionOut:
    return to_out(_get_or_404(session, txn_id))


@router.post("", response_model=TransactionOut, status_code=status.HTTP_201_CREATED)
def create_transaction(
    payload: TransactionCreate, session: Session = Depends(get_session)
) -> TransactionOut:
    _validate_refs(session, payload.account_id, payload.category_id)
    txn = Transaction(
        date=payload.date,
        amount_cents=to_cents(payload.amount),
        account_id=payload.account_id,
        category_id=payload.category_id,
        description=payload.description,
        notes=payload.notes,
    )
    session.add(txn)
    session.commit()
    session.refresh(txn)
    return to_out(txn)


@router.patch("/{txn_id}", response_model=TransactionOut)
def update_transaction(
    txn_id: int, payload: TransactionUpdate, session: Session = Depends(get_session)
) -> TransactionOut:
    txn = _get_or_404(session, txn_id)
    data = payload.model_dump(exclude_unset=True)
    _validate_refs(session, data.get("account_id"), data.get("category_id"))

    if "amount" in data:
        txn.amount_cents = to_cents(data.pop("amount"))
    for field, value in data.items():
        setattr(txn, field, value)

    session.commit()
    session.refresh(txn)
    return to_out(txn)


@router.delete("/{txn_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_transaction(txn_id: int, session: Session = Depends(get_session)) -> None:
    session.delete(_get_or_404(session, txn_id))
    session.commit()
