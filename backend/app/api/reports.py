"""Reports, CSV export, and CSV import."""

from __future__ import annotations

import json
from datetime import date as DateType
from decimal import Decimal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db import get_session
from app.models import Account, Category, Transaction
from app.services import csv_io, reports

router = APIRouter(prefix="/api/reports", tags=["reports"])


class ComparisonOut(BaseModel):
    category_id: int
    name: str
    current: Decimal
    previous: Decimal
    change: Decimal
    change_percent: float | None


class YearSummaryOut(BaseModel):
    year: int
    income: Decimal
    expenses: Decimal
    net: Decimal
    savings_rate: float | None
    months: list[dict]


class RowErrorOut(BaseModel):
    row: int
    message: str


class ImportResultOut(BaseModel):
    imported: int
    skipped: int
    errors: list[RowErrorOut]
    preview: list[dict]
    dry_run: bool


@router.get("/export.csv", response_class=PlainTextResponse)
def export_csv(
    date_from: DateType | None = Query(default=None, alias="from"),
    date_to: DateType | None = Query(default=None, alias="to"),
    session: Session = Depends(get_session),
) -> PlainTextResponse:
    stmt = (
        select(Transaction)
        .options(selectinload(Transaction.category), selectinload(Transaction.account))
        .order_by(Transaction.date)
    )
    if date_from:
        stmt = stmt.where(Transaction.date >= date_from)
    if date_to:
        stmt = stmt.where(Transaction.date <= date_to)

    body = csv_io.export_transactions(list(session.scalars(stmt)))
    filename = f"transactions-{DateType.today().isoformat()}.csv"
    return PlainTextResponse(
        body,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/import", response_model=ImportResultOut)
async def import_csv(
    file: UploadFile = File(...),
    mapping: str = Form(...),
    default_account_id: int = Form(...),
    default_category_id: int = Form(...),
    dry_run: bool = Form(True),
    session: Session = Depends(get_session),
) -> ImportResultOut:
    """Import transactions from a CSV file.

    Defaults to a dry run so the UI can show exactly what would be created —
    and which rows are broken — before anything is written.
    """
    try:
        column_map = json.loads(mapping)
    except json.JSONDecodeError:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "mapping must be valid JSON"
        )

    if session.get(Account, default_account_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Default account not found")
    if session.get(Category, default_category_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Default category not found")

    raw = await file.read()
    for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            content = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "Could not decode the file as text"
        )

    result = csv_io.import_transactions(
        session,
        content,
        column_map,
        default_account_id=default_account_id,
        default_category_id=default_category_id,
        dry_run=dry_run,
    )

    return ImportResultOut(
        imported=result.imported,
        skipped=result.skipped,
        errors=[RowErrorOut(row=e.row, message=e.message) for e in result.errors],
        preview=result.preview,
        dry_run=dry_run,
    )


@router.post("/columns")
async def detect_columns(file: UploadFile = File(...)) -> dict:
    """Read just the header row so the UI can offer a column mapping."""
    raw = await file.read(8192)
    text = raw.decode("utf-8-sig", errors="replace")
    first_line = text.splitlines()[0] if text.splitlines() else ""
    for delimiter in (";", ",", "\t"):
        if delimiter in first_line:
            return {
                "columns": [c.strip() for c in first_line.split(delimiter)],
                "delimiter": delimiter,
            }
    return {"columns": [first_line.strip()] if first_line else [], "delimiter": ","}


@router.get("/month-over-month", response_model=list[ComparisonOut])
def month_over_month(
    month: DateType | None = None, session: Session = Depends(get_session)
) -> list[ComparisonOut]:
    month = month or DateType.today()
    return [
        ComparisonOut(**vars(c)) for c in reports.month_over_month(session, month)
    ]


@router.get("/year-over-year", response_model=list[ComparisonOut])
def year_over_year(
    year: int | None = None, session: Session = Depends(get_session)
) -> list[ComparisonOut]:
    year = year or DateType.today().year
    return [ComparisonOut(**vars(c)) for c in reports.year_over_year(session, year)]


@router.get("/yearly", response_model=YearSummaryOut)
def yearly(
    year: int | None = None, session: Session = Depends(get_session)
) -> YearSummaryOut:
    year = year or DateType.today().year
    return YearSummaryOut(**vars(reports.yearly_summary(session, year)))
