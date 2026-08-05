"""Health and diagnostics."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_session
from app.models import Account, Category, Transaction

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
def health(session: Session = Depends(get_session)) -> dict:
    """Liveness plus a quick look at what's in the database."""
    return {
        "status": "ok",
        "base_currency": settings.base_currency,
        "database": str(settings.db_path),
        "counts": {
            "categories": session.scalar(select(func.count()).select_from(Category)),
            "accounts": session.scalar(select(func.count()).select_from(Account)),
            "transactions": session.scalar(
                select(func.count()).select_from(Transaction)
            ),
        },
    }
