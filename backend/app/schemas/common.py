"""Shared schema pieces.

Money crosses the API boundary as a JSON *string* decimal ("-42.50"), not a
number. JSON numbers are IEEE doubles in every JS client, so sending 42.50 as
a number reintroduces exactly the float imprecision the storage layer avoids.
Pydantic serialises `Decimal` to a string in JSON mode, which is what we want.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict

T = TypeVar("T")


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    limit: int
    offset: int


class TransactionTotals(BaseModel):
    """Totals for the current filter, not just the current page."""

    income: Decimal
    expenses: Decimal  # positive magnitude, for display
    net: Decimal


class TransactionPage(Page[T], Generic[T]):
    totals: TransactionTotals
