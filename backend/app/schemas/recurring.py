"""Schemas for recurring rules and the subscriptions view."""

from __future__ import annotations

from datetime import date as DateType
from decimal import Decimal

from pydantic import BaseModel, Field, model_validator

from app.models.base import Frequency
from app.schemas.common import ORMModel


class RecurringRuleBase(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    amount: Decimal
    category_id: int
    account_id: int
    description: str = Field(default="", max_length=255)
    frequency: Frequency
    interval: int = Field(default=1, ge=1, le=99)
    day_of_month: int | None = Field(default=None, ge=1, le=31)
    weekday: int | None = Field(default=None, ge=0, le=6)
    start_date: DateType
    end_date: DateType | None = None

    @model_validator(mode="after")
    def check(self):
        if self.amount == 0:
            raise ValueError("Amount must not be zero")
        if self.end_date and self.end_date < self.start_date:
            raise ValueError("End date must not be before the start date")
        return self


class RecurringRuleCreate(RecurringRuleBase):
    pass


class RecurringRuleUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    amount: Decimal | None = None
    category_id: int | None = None
    account_id: int | None = None
    description: str | None = Field(default=None, max_length=255)
    frequency: Frequency | None = None
    interval: int | None = Field(default=None, ge=1, le=99)
    day_of_month: int | None = Field(default=None, ge=1, le=31)
    weekday: int | None = Field(default=None, ge=0, le=6)
    start_date: DateType | None = None
    end_date: DateType | None = None
    active: bool | None = None


class RecurringRuleOut(ORMModel):
    id: int
    name: str
    amount: Decimal
    category_id: int
    account_id: int
    description: str
    frequency: Frequency
    interval: int
    day_of_month: int | None
    weekday: int | None
    start_date: DateType
    end_date: DateType | None
    active: bool
    last_generated_date: DateType | None
    # Derived, for display.
    category_name: str | None = None
    account_name: str | None = None
    monthly_equivalent: Decimal | None = None
    next_due_date: DateType | None = None


class SubscriptionsSummary(BaseModel):
    """Every active recurring expense, normalised to a comparable monthly cost."""

    items: list[RecurringRuleOut]
    total_monthly: Decimal
    total_annual: Decimal


class GenerationOut(BaseModel):
    created: int
    rules_processed: int
