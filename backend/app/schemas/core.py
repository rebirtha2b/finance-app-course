"""Request/response schemas for accounts, categories, and transactions."""

from __future__ import annotations

# Aliased: these schemas have fields *named* `date`, and a field assignment
# shadows the type in the class namespace, so `date: date | None = None` would
# later evaluate as `None | None`.
from datetime import date as DateType
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator

from app.models.base import AccountType, CategoryKind
from app.schemas.common import ORMModel

# ---------------------------------------------------------------- accounts


class AccountCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    type: AccountType = AccountType.bank
    currency: str = Field(default="EUR", min_length=3, max_length=3)
    opening_balance: Decimal = Decimal("0")

    @field_validator("currency")
    @classmethod
    def upper(cls, v: str) -> str:
        return v.upper()


class AccountUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    type: AccountType | None = None
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    opening_balance: Decimal | None = None
    archived: bool | None = None


class AccountOut(ORMModel):
    id: int
    name: str
    type: AccountType
    currency: str
    opening_balance: Decimal
    archived: bool


# -------------------------------------------------------------- categories


class CategoryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    kind: CategoryKind
    parent_id: int | None = None
    icon: str | None = Field(default=None, max_length=40)
    color: str | None = Field(default=None, max_length=20)


class CategoryUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    parent_id: int | None = None
    icon: str | None = Field(default=None, max_length=40)
    color: str | None = Field(default=None, max_length=20)
    archived: bool | None = None


class CategoryOut(ORMModel):
    id: int
    name: str
    kind: CategoryKind
    parent_id: int | None
    icon: str | None
    color: str | None
    archived: bool


class CategoryTreeOut(CategoryOut):
    children: list[CategoryOut] = []


# ------------------------------------------------------------ transactions


class TransactionBase(BaseModel):
    date: DateType
    # Signed: expenses negative, income positive. The sign is deliberately the
    # client's to set rather than being derived from the category kind, so a
    # refund can be recorded against an expense category (positive amount on
    # "Groceries") without needing a separate concept.
    amount: Decimal
    account_id: int
    category_id: int
    description: str = Field(default="", max_length=255)
    notes: str | None = None

    @field_validator("amount")
    @classmethod
    def non_zero(cls, v: Decimal) -> Decimal:
        if v == 0:
            raise ValueError("Amount must not be zero")
        return v


class TransactionCreate(TransactionBase):
    pass


class TransactionUpdate(BaseModel):
    date: DateType | None = None
    amount: Decimal | None = None
    account_id: int | None = None
    category_id: int | None = None
    description: str | None = Field(default=None, max_length=255)
    notes: str | None = None

    @field_validator("amount")
    @classmethod
    def non_zero(cls, v: Decimal | None) -> Decimal | None:
        if v is not None and v == 0:
            raise ValueError("Amount must not be zero")
        return v


class TransactionOut(ORMModel):
    id: int
    date: DateType
    amount: Decimal
    account_id: int
    category_id: int
    description: str
    notes: str | None
    recurring_rule_id: int | None
    due_date: DateType | None
    # Denormalised for display so the list doesn't need N+1 lookups client-side.
    category_name: str | None = None
    category_kind: CategoryKind | None = None
    account_name: str | None = None
