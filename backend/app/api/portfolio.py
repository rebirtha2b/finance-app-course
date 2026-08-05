"""Holdings, securities lookup, and portfolio valuation."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db import get_session
from app.models import Account, AssetType, Holding, PortfolioSnapshot, Security
from app.money import from_cents
from app.schemas.portfolio import (
    HoldingCreate,
    HoldingUpdate,
    HoldingValueOut,
    PortfolioHistoryPoint,
    PortfolioOut,
    RefreshOut,
    SecurityLookupOut,
)
from app.services import portfolio as portfolio_service
from app.services.prices import get_provider

router = APIRouter(prefix="/api", tags=["portfolio"])


@router.get("/securities/lookup", response_model=SecurityLookupOut)
def lookup_security(ticker: str) -> SecurityLookupOut:
    """Validate a symbol before a holding is created.

    Catching a typo here is the difference between a clear error and a holding
    that silently never prices.
    """
    info = get_provider().lookup(ticker)
    if info is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            f"'{ticker}' was not found. Check the symbol — European listings "
            "need a suffix, e.g. SAP.DE or ASML.AS.",
        )
    return SecurityLookupOut(
        ticker=info.ticker,
        name=info.name,
        currency=info.currency,
        exchange=info.exchange,
        asset_type=info.asset_type,
    )


def _get_or_create_security(session: Session, ticker: str) -> Security:
    existing = session.scalar(select(Security).where(Security.ticker == ticker))
    if existing:
        return existing

    info = get_provider().lookup(ticker)
    if info is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            f"'{ticker}' was not found. Check the symbol — European listings "
            "need a suffix, e.g. SAP.DE or ASML.AS.",
        )

    try:
        asset_type = AssetType(info.asset_type)
    except ValueError:
        asset_type = AssetType.other

    security = Security(
        ticker=info.ticker,
        name=info.name,
        currency=info.currency,
        exchange=info.exchange,
        asset_type=asset_type,
    )
    session.add(security)
    session.flush()
    return security


@router.get("/holdings", response_model=list[HoldingValueOut])
def list_holdings(session: Session = Depends(get_session)) -> list[HoldingValueOut]:
    valuation = portfolio_service.value_portfolio(session)
    return [HoldingValueOut(**vars(h)) for h in valuation.holdings]


@router.post("/holdings", response_model=HoldingValueOut, status_code=status.HTTP_201_CREATED)
def create_holding(
    payload: HoldingCreate, session: Session = Depends(get_session)
) -> HoldingValueOut:
    if payload.account_id is not None and session.get(Account, payload.account_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Account not found")

    security = _get_or_create_security(session, payload.ticker)

    duplicate = session.scalar(
        select(Holding).where(
            Holding.security_id == security.id, Holding.account_id == payload.account_id
        )
    )
    if duplicate:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"You already hold {security.ticker} in this account; edit the quantity instead.",
        )

    holding = Holding(
        security_id=security.id,
        account_id=payload.account_id,
        quantity=payload.quantity,
        avg_cost_price=payload.avg_cost_price,
        notes=payload.notes,
    )
    session.add(holding)
    session.commit()

    # Price it immediately so a newly added holding is not blank until the
    # next scheduled refresh.
    try:
        portfolio_service.refresh_prices(session)
    except Exception:  # pragma: no cover - defensive
        pass

    valuation = portfolio_service.value_portfolio(session)
    row = next(h for h in valuation.holdings if h.holding_id == holding.id)
    return HoldingValueOut(**vars(row))


def _get_or_404(session: Session, holding_id: int) -> Holding:
    holding = session.get(Holding, holding_id)
    if holding is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Holding not found")
    return holding


@router.patch("/holdings/{holding_id}", response_model=HoldingValueOut)
def update_holding(
    holding_id: int, payload: HoldingUpdate, session: Session = Depends(get_session)
) -> HoldingValueOut:
    holding = _get_or_404(session, holding_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(holding, field, value)
    session.commit()

    valuation = portfolio_service.value_portfolio(session)
    row = next(h for h in valuation.holdings if h.holding_id == holding.id)
    return HoldingValueOut(**vars(row))


@router.delete("/holdings/{holding_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_holding(holding_id: int, session: Session = Depends(get_session)) -> None:
    # The Security and its price history stay: they cost nothing to keep and
    # mean re-adding the holding later is instant and already priced.
    session.delete(_get_or_404(session, holding_id))
    session.commit()


@router.get("/portfolio", response_model=PortfolioOut)
def get_portfolio(
    on: date | None = None, session: Session = Depends(get_session)
) -> PortfolioOut:
    valuation = portfolio_service.value_portfolio(session, on)
    return PortfolioOut(
        holdings=[HoldingValueOut(**vars(h)) for h in valuation.holdings],
        total_value_base=valuation.total_value_base,
        total_cost_base=valuation.total_cost_base,
        total_gain_base=valuation.total_gain_base,
        total_gain_percent=valuation.total_gain_percent,
        day_change_base=valuation.day_change_base,
        base_currency=valuation.base_currency,
        prices_as_of=valuation.prices_as_of,
        has_stale_prices=valuation.has_stale_prices,
        missing_prices=valuation.missing_prices,
    )


@router.post("/portfolio/refresh", response_model=RefreshOut)
def refresh(session: Session = Depends(get_session)) -> RefreshOut:
    result = portfolio_service.refresh_prices(session)
    portfolio_service.record_snapshot(session)
    return RefreshOut(
        prices_updated=result.prices_updated,
        fx_updated=result.fx_updated,
        failed_tickers=result.failed_tickers,
        failed_fx=result.failed_fx,
        ok=result.ok,
    )


@router.get("/portfolio/history", response_model=list[PortfolioHistoryPoint])
def history(session: Session = Depends(get_session)) -> list[PortfolioHistoryPoint]:
    rows = session.scalars(
        select(PortfolioSnapshot).order_by(PortfolioSnapshot.date)
    )
    return [
        PortfolioHistoryPoint(
            date=r.date,
            total_value=from_cents(r.total_value_cents),
            total_cost=(
                from_cents(r.total_cost_cents) if r.total_cost_cents is not None else None
            ),
        )
        for r in rows
    ]
