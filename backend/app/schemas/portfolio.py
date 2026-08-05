"""Portfolio schemas."""

from __future__ import annotations

from datetime import date as DateType
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator

from app.schemas.common import ORMModel


class HoldingCreate(BaseModel):
    ticker: str = Field(min_length=1, max_length=30)
    quantity: Decimal = Field(gt=0)
    avg_cost_price: Decimal | None = Field(default=None, gt=0)
    account_id: int | None = None
    notes: str | None = None

    @field_validator("ticker")
    @classmethod
    def normalise(cls, v: str) -> str:
        return v.strip().upper()


class HoldingUpdate(BaseModel):
    quantity: Decimal | None = Field(default=None, gt=0)
    avg_cost_price: Decimal | None = Field(default=None, gt=0)
    account_id: int | None = None
    notes: str | None = None


class SecurityOut(ORMModel):
    id: int
    ticker: str
    name: str
    exchange: str | None
    currency: str
    asset_type: str


class SecurityLookupOut(BaseModel):
    ticker: str
    name: str
    currency: str
    exchange: str | None = None
    asset_type: str = "stock"


class HoldingValueOut(BaseModel):
    holding_id: int
    security_id: int
    ticker: str
    name: str
    currency: str
    quantity: Decimal
    price: Decimal | None
    price_date: DateType | None
    value_native: Decimal | None
    value_base: Decimal | None
    day_change_base: Decimal | None
    day_change_percent: float | None
    cost_basis_base: Decimal | None
    gain_base: Decimal | None
    gain_percent: float | None
    allocation_percent: float
    stale: bool


class PortfolioOut(BaseModel):
    holdings: list[HoldingValueOut]
    total_value_base: Decimal
    total_cost_base: Decimal | None
    total_gain_base: Decimal | None
    total_gain_percent: float | None
    day_change_base: Decimal
    base_currency: str
    prices_as_of: DateType | None
    has_stale_prices: bool
    missing_prices: list[str]


class RefreshOut(BaseModel):
    prices_updated: int
    fx_updated: int
    failed_tickers: list[str]
    failed_fx: list[str]
    ok: bool


class PortfolioHistoryPoint(BaseModel):
    date: DateType
    total_value: Decimal
    total_cost: Decimal | None
