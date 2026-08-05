"""SQLAlchemy models.

Importing this package registers every model on `Base.metadata`, which is what
Alembic autogenerate and `create_all` rely on.
"""

from app.models.base import (
    AccountType,
    AssetType,
    Base,
    BudgetPeriod,
    CategoryKind,
    Frequency,
    TimestampMixin,
    utcnow,
)
from app.models.core import Account, Budget, Category, RecurringRule, Transaction
from app.models.portfolio import (
    FxRate,
    Holding,
    PortfolioSnapshot,
    PriceSnapshot,
    Security,
)

__all__ = [
    "Account",
    "AccountType",
    "AssetType",
    "Base",
    "Budget",
    "BudgetPeriod",
    "Category",
    "CategoryKind",
    "Frequency",
    "FxRate",
    "Holding",
    "PortfolioSnapshot",
    "PriceSnapshot",
    "RecurringRule",
    "Security",
    "TimestampMixin",
    "Transaction",
    "utcnow",
]
