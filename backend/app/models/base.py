"""Declarative base and shared enums."""

from __future__ import annotations

import enum
from datetime import datetime, timezone

from sqlalchemy import DateTime
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


class CategoryKind(str, enum.Enum):
    income = "income"
    expense = "expense"


class AccountType(str, enum.Enum):
    cash = "cash"
    bank = "bank"
    broker = "broker"


class Frequency(str, enum.Enum):
    daily = "daily"
    weekly = "weekly"
    monthly = "monthly"
    quarterly = "quarterly"
    yearly = "yearly"


class BudgetPeriod(str, enum.Enum):
    monthly = "monthly"
    yearly = "yearly"


class AssetType(str, enum.Enum):
    stock = "stock"
    etf = "etf"
    fund = "fund"
    other = "other"
