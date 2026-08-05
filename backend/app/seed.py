"""First-run seed data: the default category tree and a starting account.

Idempotent by design — it runs on every startup and only inserts what is
missing, so it never duplicates or overwrites categories you have renamed.
Deleting a seeded category will not bring it back, because we key on name and
only add when absent... which means a category you deliberately removed WILL
reappear. Archive it instead of deleting it if you want it gone for good.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Account, AccountType, Category, CategoryKind

# (parent, [children]) — two levels, matching the model's constraint.
EXPENSE_TREE: list[tuple[str, list[str]]] = [
    ("Housing", ["Rent", "Utilities", "Internet", "Maintenance"]),
    ("Food", ["Groceries", "Restaurants", "Delivery"]),
    ("Transport", ["Fuel", "Public transit", "Car insurance", "Repairs"]),
    ("Subscriptions", ["Streaming", "Software", "Cloud storage", "Gym", "Phone"]),
    ("Health", ["Health insurance", "Pharmacy", "Doctor"]),
    ("Shopping", ["Clothing", "Electronics", "Household"]),
    ("Entertainment", []),
    ("Travel", []),
    ("Education", []),
    ("Gifts & donations", []),
    ("Fees & interest", []),
    ("Taxes", []),
    ("Other expenses", []),
]

INCOME_TREE: list[tuple[str, list[str]]] = [
    ("Salary", []),
    ("Bonus", []),
    ("Freelance", []),
    ("Dividends", []),
    ("Interest", []),
    ("Refunds", []),
    ("Rental income", []),
    ("Other income", []),
]

# Muted, distinguishable hues for the spending donut. Deliberately not the
# saturated default palette every charting library ships with.
PARENT_COLORS = {
    "Housing": "#6366f1",
    "Food": "#10b981",
    "Transport": "#f59e0b",
    "Subscriptions": "#ec4899",
    "Health": "#ef4444",
    "Shopping": "#8b5cf6",
    "Entertainment": "#06b6d4",
    "Travel": "#14b8a6",
    "Education": "#3b82f6",
    "Gifts & donations": "#f97316",
    "Fees & interest": "#64748b",
    "Taxes": "#78716c",
    "Other expenses": "#94a3b8",
    "Salary": "#22c55e",
    "Bonus": "#84cc16",
    "Freelance": "#0ea5e9",
    "Dividends": "#a855f7",
    "Interest": "#2dd4bf",
    "Refunds": "#facc15",
    "Rental income": "#fb7185",
    "Other income": "#94a3b8",
}


def _get_or_create_category(
    session: Session,
    name: str,
    kind: CategoryKind,
    parent_id: int | None,
    color: str | None = None,
) -> Category:
    existing = session.scalar(
        select(Category).where(Category.name == name, Category.parent_id == parent_id)
    )
    if existing is not None:
        return existing
    category = Category(name=name, kind=kind, parent_id=parent_id, color=color)
    session.add(category)
    session.flush()  # assign the id so children can reference it
    return category


def seed_categories(session: Session) -> int:
    """Insert any missing default categories. Returns the number created."""
    created = 0

    for kind, tree in (
        (CategoryKind.expense, EXPENSE_TREE),
        (CategoryKind.income, INCOME_TREE),
    ):
        for parent_name, child_names in tree:
            existing_parent = session.scalar(
                select(Category).where(
                    Category.name == parent_name, Category.parent_id.is_(None)
                )
            )
            parent = existing_parent or _get_or_create_category(
                session, parent_name, kind, None, PARENT_COLORS.get(parent_name)
            )
            if existing_parent is None:
                created += 1

            for child_name in child_names:
                existing_child = session.scalar(
                    select(Category).where(
                        Category.name == child_name, Category.parent_id == parent.id
                    )
                )
                if existing_child is None:
                    _get_or_create_category(session, child_name, kind, parent.id)
                    created += 1

    return created


def seed_accounts(session: Session) -> int:
    """Create one default account so transactions can be entered immediately."""
    if session.scalar(select(Account.id).limit(1)) is not None:
        return 0
    session.add(
        Account(name="Main account", type=AccountType.bank, currency="EUR")
    )
    return 1


def run_seed(session: Session) -> dict[str, int]:
    result = {
        "categories_created": seed_categories(session),
        "accounts_created": seed_accounts(session),
    }
    session.commit()
    return result
