"""Account CRUD."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import Account, Transaction
from app.money import from_cents, to_cents
from app.schemas.core import AccountCreate, AccountOut, AccountUpdate

router = APIRouter(prefix="/api/accounts", tags=["accounts"])


def to_out(account: Account) -> AccountOut:
    return AccountOut(
        id=account.id,
        name=account.name,
        type=account.type,
        currency=account.currency,
        opening_balance=from_cents(account.opening_balance_cents),
        archived=account.archived,
    )


@router.get("", response_model=list[AccountOut])
def list_accounts(
    include_archived: bool = False, session: Session = Depends(get_session)
) -> list[AccountOut]:
    stmt = select(Account).order_by(Account.name)
    if not include_archived:
        stmt = stmt.where(Account.archived.is_(False))
    return [to_out(a) for a in session.scalars(stmt)]


@router.post("", response_model=AccountOut, status_code=status.HTTP_201_CREATED)
def create_account(
    payload: AccountCreate, session: Session = Depends(get_session)
) -> AccountOut:
    if session.scalar(select(Account).where(Account.name == payload.name)):
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with that name exists")
    account = Account(
        name=payload.name,
        type=payload.type,
        currency=payload.currency,
        opening_balance_cents=to_cents(payload.opening_balance),
    )
    session.add(account)
    session.commit()
    return to_out(account)


def _get_or_404(session: Session, account_id: int) -> Account:
    account = session.get(Account, account_id)
    if account is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Account not found")
    return account


@router.patch("/{account_id}", response_model=AccountOut)
def update_account(
    account_id: int, payload: AccountUpdate, session: Session = Depends(get_session)
) -> AccountOut:
    account = _get_or_404(session, account_id)
    data = payload.model_dump(exclude_unset=True)
    if "opening_balance" in data:
        account.opening_balance_cents = to_cents(data.pop("opening_balance"))
    for field, value in data.items():
        setattr(account, field, value)
    session.commit()
    return to_out(account)


@router.delete("/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_account(account_id: int, session: Session = Depends(get_session)) -> None:
    account = _get_or_404(session, account_id)
    in_use = session.scalar(
        select(Transaction.id).where(Transaction.account_id == account_id).limit(1)
    )
    if in_use:
        # Deleting would either orphan or silently destroy history. Archiving
        # hides it from pickers while keeping past transactions intact.
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Account has transactions; archive it instead of deleting.",
        )
    session.delete(account)
    session.commit()
