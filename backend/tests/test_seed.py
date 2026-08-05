from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Account, Category, CategoryKind
from app.seed import run_seed


def test_seed_creates_category_tree(session: Session) -> None:
    result = run_seed(session)
    assert result["categories_created"] > 0
    assert result["accounts_created"] == 1

    total = session.scalar(select(func.count()).select_from(Category))
    assert total == result["categories_created"]

    # Both kinds present, and the tree is two levels deep.
    kinds = set(session.scalars(select(Category.kind)).all())
    assert kinds == {CategoryKind.income, CategoryKind.expense}

    subscriptions = session.scalar(
        select(Category).where(Category.name == "Subscriptions")
    )
    assert subscriptions is not None
    assert {c.name for c in subscriptions.children} >= {"Streaming", "Gym"}
    # Children must not have children of their own.
    for child in subscriptions.children:
        assert child.children == []


def test_seed_is_idempotent(session: Session) -> None:
    """Startup runs the seed every time; a second run must be a no-op."""
    first = run_seed(session)
    count_after_first = session.scalar(select(func.count()).select_from(Category))

    second = run_seed(session)
    assert second["categories_created"] == 0
    assert second["accounts_created"] == 0
    assert session.scalar(select(func.count()).select_from(Category)) == count_after_first
    assert session.scalar(select(func.count()).select_from(Account)) == 1


def test_seed_does_not_overwrite_renamed_categories(session: Session) -> None:
    run_seed(session)
    rent = session.scalar(select(Category).where(Category.name == "Rent"))
    rent.name = "Rent & service charge"
    session.commit()

    run_seed(session)

    # The rename survives; the seed re-adds "Rent" rather than clobbering it,
    # which is the safe direction for user-edited data.
    assert session.scalar(
        select(Category).where(Category.name == "Rent & service charge")
    ) is not None
