"""Cash-flow models: accounts, categories, transactions, recurring rules, budgets."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Date,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import (
    AccountType,
    Base,
    BudgetPeriod,
    CategoryKind,
    Frequency,
    TimestampMixin,
)
from app.money import ExactDecimal


class Account(Base, TimestampMixin):
    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    type: Mapped[AccountType] = mapped_column(
        Enum(AccountType, native_enum=False), nullable=False, default=AccountType.bank
    )
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="EUR")
    opening_balance_cents: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    transactions: Mapped[list["Transaction"]] = relationship(back_populates="account")


class Category(Base, TimestampMixin):
    __tablename__ = "categories"
    __table_args__ = (UniqueConstraint("name", "parent_id", name="uq_category_name_parent"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    kind: Mapped[CategoryKind] = mapped_column(
        Enum(CategoryKind, native_enum=False), nullable=False
    )
    # Two levels only: a parent is a top-level category, children are leaves.
    parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("categories.id", ondelete="RESTRICT"), nullable=True
    )
    icon: Mapped[str | None] = mapped_column(String(40), nullable=True)
    color: Mapped[str | None] = mapped_column(String(20), nullable=True)
    archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    parent: Mapped["Category | None"] = relationship(
        back_populates="children", remote_side=[id]
    )
    children: Mapped[list["Category"]] = relationship(back_populates="parent")


class Transaction(Base, TimestampMixin):
    __tablename__ = "transactions"
    __table_args__ = (
        Index("ix_transactions_date", "date"),
        Index("ix_transactions_category_date", "category_id", "date"),
        # Guarantees recurring generation is idempotent: a given rule can
        # produce at most one transaction per due date, so re-running the
        # generator (startup + daily job overlapping) cannot double-charge.
        UniqueConstraint(
            "recurring_rule_id", "due_date", name="uq_transaction_rule_due_date"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    date: Mapped[date] = mapped_column(Date, nullable=False)

    # Signed, in base currency (EUR): expenses negative, income positive.
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)

    # Set only when the transaction was entered in a foreign currency; kept so
    # the original figure stays visible instead of being lost to conversion.
    original_currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    original_amount_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fx_rate: Mapped[Decimal | None] = mapped_column(ExactDecimal(40), nullable=True)

    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=False
    )
    category_id: Mapped[int] = mapped_column(
        ForeignKey("categories.id", ondelete="RESTRICT"), nullable=False
    )
    description: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    recurring_rule_id: Mapped[int | None] = mapped_column(
        ForeignKey("recurring_rules.id", ondelete="SET NULL"), nullable=True
    )
    # The scheduled date this row satisfies. Differs from `date` only if the
    # user edits the actual date; the pairing with the rule stays intact.
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    account: Mapped[Account] = relationship(back_populates="transactions")
    category: Mapped[Category] = relationship()
    recurring_rule: Mapped["RecurringRule | None"] = relationship(
        back_populates="transactions"
    )


class RecurringRule(Base, TimestampMixin):
    __tablename__ = "recurring_rules"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)

    # Template for generated transactions.
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    category_id: Mapped[int] = mapped_column(
        ForeignKey("categories.id", ondelete="RESTRICT"), nullable=False
    )
    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=False
    )
    description: Mapped[str] = mapped_column(String(255), nullable=False, default="")

    frequency: Mapped[Frequency] = mapped_column(
        Enum(Frequency, native_enum=False), nullable=False
    )
    # Every `interval` periods, e.g. interval=3 + frequency=monthly.
    interval: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    # For monthly/quarterly/yearly. 31 means "last day" in shorter months.
    day_of_month: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # For weekly: 0=Monday .. 6=Sunday.
    weekday: Mapped[int | None] = mapped_column(Integer, nullable=True)

    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_generated_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    category: Mapped[Category] = relationship()
    account: Mapped[Account] = relationship()
    transactions: Mapped[list[Transaction]] = relationship(
        back_populates="recurring_rule"
    )


class Budget(Base, TimestampMixin):
    __tablename__ = "budgets"
    __table_args__ = (
        UniqueConstraint("category_id", "period", name="uq_budget_category_period"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    category_id: Mapped[int] = mapped_column(
        ForeignKey("categories.id", ondelete="CASCADE"), nullable=False
    )
    period: Mapped[BudgetPeriod] = mapped_column(
        Enum(BudgetPeriod, native_enum=False), nullable=False, default=BudgetPeriod.monthly
    )
    # Always positive: a limit is a magnitude, while spending is stored negative.
    limit_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    start_month: Mapped[date] = mapped_column(Date, nullable=False)
    rollover: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    category: Mapped[Category] = relationship()
