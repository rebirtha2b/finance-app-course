"""Budget schemas."""

from __future__ import annotations

from datetime import date as DateType
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator

from app.models.base import BudgetPeriod
from app.schemas.common import ORMModel


class BudgetCreate(BaseModel):
    category_id: int
    period: BudgetPeriod = BudgetPeriod.monthly
    # A limit is a magnitude, always positive, even though spending is stored
    # negative. Accepting a negative here would be ambiguous.
    limit: Decimal = Field(gt=0)
    start_month: DateType | None = None
    rollover: bool = False

    @field_validator("start_month")
    @classmethod
    def normalise_to_first(cls, v: DateType | None) -> DateType | None:
        return v.replace(day=1) if v else None


class BudgetUpdate(BaseModel):
    limit: Decimal | None = Field(default=None, gt=0)
    period: BudgetPeriod | None = None
    start_month: DateType | None = None
    rollover: bool | None = None
    active: bool | None = None

    @field_validator("start_month")
    @classmethod
    def normalise_to_first(cls, v: DateType | None) -> DateType | None:
        return v.replace(day=1) if v else None


class BudgetOut(ORMModel):
    id: int
    category_id: int
    period: BudgetPeriod
    limit: Decimal
    start_month: DateType
    rollover: bool
    active: bool
    category_name: str | None = None


class BudgetStatusOut(BaseModel):
    budget_id: int
    category_id: int
    category_name: str
    period: BudgetPeriod
    limit: Decimal
    effective_limit: Decimal
    spent: Decimal
    remaining: Decimal
    rollover: Decimal
    percent_used: float
    over_budget: bool
    window_start: DateType
    window_end: DateType


class BudgetStatusSummary(BaseModel):
    month: DateType
    items: list[BudgetStatusOut]
    total_limit: Decimal
    total_spent: Decimal
    total_remaining: Decimal
