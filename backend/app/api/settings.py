"""Data management: what's stored, and deleting it.

Reset is the only irreversible action in the app, so it is deliberately
awkward: the caller must name the scopes explicitly *and* send an exact
confirmation phrase. Neither alone is enough, which makes an accidental
DELETE against this endpoint a no-op rather than a catastrophe.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import (
    Account,
    Budget,
    Category,
    FxRate,
    Holding,
    PortfolioSnapshot,
    PriceSnapshot,
    RecurringRule,
    Security,
    Transaction,
)
from app.seed import run_seed

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/settings", tags=["settings"])

# Typed by the user, character for character, before anything is deleted.
CONFIRMATION_PHRASE = "DELETE MY DATA"

VALID_SCOPES = {"transactions", "recurring", "budgets", "portfolio", "categories"}


class DataSummary(BaseModel):
    transactions: int
    recurring_rules: int
    budgets: int
    holdings: int
    securities: int
    price_snapshots: int
    categories: int
    accounts: int


class ResetRequest(BaseModel):
    scopes: list[str] = Field(min_length=1)
    confirm: str


class ResetResult(BaseModel):
    deleted: dict[str, int]
    scopes: list[str]
    categories_restored: int


def _count(session: Session, model) -> int:
    return session.scalar(select(func.count()).select_from(model)) or 0


@router.get("/data-summary", response_model=DataSummary)
def data_summary(session: Session = Depends(get_session)) -> DataSummary:
    """What is currently stored — shown before any destructive action."""
    return DataSummary(
        transactions=_count(session, Transaction),
        recurring_rules=_count(session, RecurringRule),
        budgets=_count(session, Budget),
        holdings=_count(session, Holding),
        securities=_count(session, Security),
        price_snapshots=_count(session, PriceSnapshot),
        categories=_count(session, Category),
        accounts=_count(session, Account),
    )


@router.post("/reset", response_model=ResetResult)
def reset_data(
    payload: ResetRequest, session: Session = Depends(get_session)
) -> ResetResult:
    """Permanently delete the selected data. There is no undo.

    Deletion order follows the foreign keys: transactions reference rules,
    categories and accounts, and holdings reference securities. Getting the
    order wrong would trip the FK constraints rather than corrupting anything,
    but the explicit ordering documents the dependency.
    """
    if payload.confirm != CONFIRMATION_PHRASE:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f'Type "{CONFIRMATION_PHRASE}" exactly to confirm. Nothing was deleted.',
        )

    unknown = set(payload.scopes) - VALID_SCOPES
    if unknown:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"Unknown scope(s): {', '.join(sorted(unknown))}. Nothing was deleted.",
        )

    scopes = set(payload.scopes)
    deleted: dict[str, int] = {}

    def wipe(label: str, model) -> None:
        count = _count(session, model)
        if count:
            session.execute(delete(model))
            deleted[label] = count

    # Clearing categories would orphan every transaction, rule and budget that
    # references one, so it implies clearing those too rather than failing.
    if "categories" in scopes:
        scopes |= {"transactions", "recurring", "budgets"}

    if "transactions" in scopes:
        wipe("transactions", Transaction)

    if "recurring" in scopes:
        # Any surviving transactions detach via ON DELETE SET NULL — the money
        # still moved, so the history stays even without its rule.
        wipe("recurring_rules", RecurringRule)

    if "budgets" in scopes:
        wipe("budgets", Budget)

    if "portfolio" in scopes:
        wipe("holdings", Holding)
        wipe("portfolio_snapshots", PortfolioSnapshot)
        wipe("price_snapshots", PriceSnapshot)
        wipe("securities", Security)
        wipe("fx_rates", FxRate)

    restored = 0
    if "categories" in scopes:
        # Categories reference themselves via parent_id, and SQLite enforces
        # foreign keys row by row, so a single DELETE trips the constraint on
        # whichever parent it happens to reach first. Children go first.
        total = _count(session, Category)
        if total:
            session.execute(delete(Category).where(Category.parent_id.isnot(None)))
            session.flush()
            session.execute(delete(Category).where(Category.parent_id.is_(None)))
            deleted["categories"] = total
        wipe("accounts", Account)
        session.flush()
        # Without this the app would come back with no categories and no
        # account, and nothing could be entered at all.
        result = run_seed(session)
        restored = result["categories_created"]

    session.commit()
    logger.warning("Data reset performed. Scopes: %s. Deleted: %s", sorted(scopes), deleted)

    return ResetResult(
        deleted=deleted, scopes=sorted(scopes), categories_restored=restored
    )
