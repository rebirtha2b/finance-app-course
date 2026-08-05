"""CSV export and import.

Import is deliberately strict and reports per-row problems rather than doing
its best and silently miscategorising things. A bank export with one bad date
should tell you which row it was, not quietly land 300 transactions in
"Other".
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Account, Category, Transaction
from app.money import from_cents, to_cents

EXPORT_COLUMNS = [
    "date",
    "amount",
    "description",
    "category",
    "account",
    "notes",
    "recurring",
]

# Formats seen in real bank exports, tried in order.
DATE_FORMATS = ["%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y", "%Y/%m/%d"]


def export_transactions(transactions: list[Transaction]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(EXPORT_COLUMNS)

    for txn in transactions:
        writer.writerow(
            [
                txn.date.isoformat(),
                str(from_cents(txn.amount_cents)),
                txn.description,
                txn.category.name if txn.category else "",
                txn.account.name if txn.account else "",
                txn.notes or "",
                "yes" if txn.recurring_rule_id else "",
            ]
        )
    return buffer.getvalue()


def parse_date(raw: str) -> date | None:
    raw = raw.strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def parse_amount(raw: str) -> Decimal | None:
    """Parse an amount from a bank export.

    Handles "1.234,56" (German), "1,234.56" (English), currency symbols, and
    a trailing minus. Returns None if it cannot be read confidently — better
    to flag the row than to guess at someone's money.
    """
    text = raw.strip().replace("€", "").replace("$", "").replace("£", "").replace(" ", "")
    if not text:
        return None

    # Trailing minus, as some exports do ("123.45-").
    negative = text.endswith("-")
    if negative:
        text = text[:-1]

    has_comma, has_dot = "," in text, "." in text
    if has_comma and has_dot:
        # Whichever appears last is the decimal separator.
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif has_comma:
        # A lone comma is a decimal separator if it has 1-2 digits after it.
        after = text.split(",")[-1]
        text = text.replace(",", "." if len(after) <= 2 else "")

    try:
        value = Decimal(text)
    except InvalidOperation:
        return None
    return -value if negative else value


@dataclass
class RowError:
    row: int
    message: str
    raw: dict


@dataclass
class ImportResult:
    imported: int = 0
    skipped: int = 0
    errors: list[RowError] = field(default_factory=list)
    # Populated on a dry run so the UI can show what would happen.
    preview: list[dict] = field(default_factory=list)


def import_transactions(
    session: Session,
    content: str,
    mapping: dict[str, str],
    default_account_id: int,
    default_category_id: int,
    dry_run: bool = True,
) -> ImportResult:
    """Import rows from CSV text.

    `mapping` maps our field names (date, amount, description, category,
    account, notes) to the incoming file's column headers.
    """
    result = ImportResult()

    # Sniff the delimiter: European exports are frequently semicolon-separated.
    sample = content[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
        delimiter = dialect.delimiter
    except csv.Error:
        delimiter = ","

    reader = csv.DictReader(io.StringIO(content), delimiter=delimiter)

    categories = {
        c.name.strip().lower(): c for c in session.scalars(select(Category))
    }
    accounts = {a.name.strip().lower(): a for a in session.scalars(select(Account))}

    date_col = mapping.get("date")
    amount_col = mapping.get("amount")
    if not date_col or not amount_col:
        result.errors.append(
            RowError(row=0, message="A date column and an amount column are required", raw={})
        )
        return result

    for index, row in enumerate(reader, start=2):  # row 1 is the header
        raw_date = (row.get(date_col) or "").strip()
        raw_amount = (row.get(amount_col) or "").strip()

        if not raw_date and not raw_amount:
            result.skipped += 1
            continue

        parsed_date = parse_date(raw_date)
        if parsed_date is None:
            result.errors.append(
                RowError(row=index, message=f"Could not read the date {raw_date!r}", raw=row)
            )
            continue

        amount = parse_amount(raw_amount)
        if amount is None:
            result.errors.append(
                RowError(row=index, message=f"Could not read the amount {raw_amount!r}", raw=row)
            )
            continue
        if amount == 0:
            result.errors.append(
                RowError(row=index, message="Amount is zero", raw=row)
            )
            continue

        category = None
        if mapping.get("category"):
            name = (row.get(mapping["category"]) or "").strip().lower()
            category = categories.get(name)
        category_id = category.id if category else default_category_id

        account = None
        if mapping.get("account"):
            name = (row.get(mapping["account"]) or "").strip().lower()
            account = accounts.get(name)
        account_id = account.id if account else default_account_id

        description = (
            (row.get(mapping["description"]) or "").strip()
            if mapping.get("description")
            else ""
        )
        notes = (
            (row.get(mapping["notes"]) or "").strip() if mapping.get("notes") else None
        )

        if dry_run:
            if len(result.preview) < 20:
                result.preview.append(
                    {
                        "date": parsed_date.isoformat(),
                        "amount": str(amount),
                        "description": description,
                        "category": category.name if category else "(default)",
                        "account": account.name if account else "(default)",
                    }
                )
        else:
            session.add(
                Transaction(
                    date=parsed_date,
                    amount_cents=to_cents(amount),
                    account_id=account_id,
                    category_id=category_id,
                    description=description,
                    notes=notes or None,
                )
            )
        result.imported += 1

    if not dry_run:
        session.commit()

    return result
