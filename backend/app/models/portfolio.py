"""Portfolio models: securities, holdings, cached prices and FX rates."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import AssetType, Base, TimestampMixin
from app.money import ExactDecimal


class Security(Base, TimestampMixin):
    __tablename__ = "securities"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Provider-native symbol, e.g. AAPL, SAP.DE, ASML.AS.
    ticker: Mapped[str] = mapped_column(String(30), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False, default="")
    exchange: Mapped[str | None] = mapped_column(String(40), nullable=True)
    # The currency the security is quoted in, not the user's base currency.
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    asset_type: Mapped[AssetType] = mapped_column(
        Enum(AssetType, native_enum=False), nullable=False, default=AssetType.stock
    )

    holdings: Mapped[list["Holding"]] = relationship(back_populates="security")
    prices: Mapped[list["PriceSnapshot"]] = relationship(back_populates="security")


class Holding(Base, TimestampMixin):
    __tablename__ = "holdings"
    __table_args__ = (
        UniqueConstraint("security_id", "account_id", name="uq_holding_security_account"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    security_id: Mapped[int] = mapped_column(
        ForeignKey("securities.id", ondelete="CASCADE"), nullable=False
    )
    account_id: Mapped[int | None] = mapped_column(
        ForeignKey("accounts.id", ondelete="SET NULL"), nullable=True
    )
    # Exact decimal: fractional shares are common with modern brokers.
    quantity: Mapped[Decimal] = mapped_column(ExactDecimal(40), nullable=False)
    # Optional, in the security's own currency. Drives gain/loss when present.
    avg_cost_price: Mapped[Decimal | None] = mapped_column(ExactDecimal(40), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    security: Mapped[Security] = relationship(back_populates="holdings")


class PriceSnapshot(Base):
    """One daily close per security.

    Kept as history rather than a single latest-price column: it gives the
    portfolio-over-time chart for free, and lets a failed fetch fall back to
    the last known good price instead of rendering zeros.
    """

    __tablename__ = "price_snapshots"
    __table_args__ = (
        UniqueConstraint("security_id", "date", name="uq_price_security_date"),
        Index("ix_price_security_date", "security_id", "date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    security_id: Mapped[int] = mapped_column(
        ForeignKey("securities.id", ondelete="CASCADE"), nullable=False
    )
    date: Mapped[date] = mapped_column(Date, nullable=False)
    close_price: Mapped[Decimal] = mapped_column(ExactDecimal(40), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    security: Mapped[Security] = relationship(back_populates="prices")


class FxRate(Base):
    __tablename__ = "fx_rates"
    __table_args__ = (
        UniqueConstraint("base", "quote", "date", name="uq_fx_base_quote_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    base: Mapped[str] = mapped_column(String(3), nullable=False)
    quote: Mapped[str] = mapped_column(String(3), nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    # Multiply an amount in `base` by this to get `quote`.
    rate: Mapped[Decimal] = mapped_column(ExactDecimal(40), nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PortfolioSnapshot(Base):
    """Daily total portfolio value, for the history chart."""

    __tablename__ = "portfolio_snapshots"
    __table_args__ = (UniqueConstraint("date", name="uq_portfolio_snapshot_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    total_value_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    total_cost_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
