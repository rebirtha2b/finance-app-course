from __future__ import annotations

import json
from datetime import date
from decimal import Decimal

import pytest


@pytest.fixture()
def refs(client) -> dict:
    categories = client.get("/api/categories", params={"include_archived": True}).json()
    by_name = {c["name"]: c for c in categories}
    return {
        "account": client.get("/api/accounts").json()[0],
        "groceries": by_name["Groceries"],
        "restaurants": by_name["Restaurants"],
        "rent": by_name["Rent"],
        "salary": by_name["Salary"],
        "other": by_name["Other expenses"],
    }


def add(client, refs, amount: str, category: str, when: str, desc: str = "x") -> None:
    resp = client.post(
        "/api/transactions",
        json={
            "date": when,
            "amount": amount,
            "account_id": refs["account"]["id"],
            "category_id": refs[category]["id"],
            "description": desc,
        },
    )
    assert resp.status_code == 201, resp.text


# ------------------------------------------------------------------ export


def test_export_produces_readable_csv(client, refs) -> None:
    add(client, refs, "-12.34", "groceries", "2026-08-01", "Supermarket")
    add(client, refs, "2500.00", "salary", "2026-08-01", "Salary")

    resp = client.get("/api/reports/export.csv")
    assert resp.status_code == 200
    assert "attachment" in resp.headers["content-disposition"]

    lines = resp.text.strip().splitlines()
    assert lines[0] == "date,amount,description,category,account,notes,recurring"
    assert any("Supermarket" in line and "-12.34" in line for line in lines)
    assert any("Salary" in line and "2500.00" in line for line in lines)


def test_export_respects_date_filter(client, refs) -> None:
    add(client, refs, "-10.00", "groceries", "2026-07-15")
    add(client, refs, "-20.00", "groceries", "2026-08-15")

    resp = client.get(
        "/api/reports/export.csv", params={"from": "2026-08-01", "to": "2026-08-31"}
    )
    lines = resp.text.strip().splitlines()
    assert len(lines) == 2  # header + one row
    assert "-20.00" in lines[1]


# ------------------------------------------------------------------ import


def upload(client, refs, csv_text: str, mapping: dict, dry_run: bool = True):
    return client.post(
        "/api/reports/import",
        files={"file": ("bank.csv", csv_text.encode("utf-8"), "text/csv")},
        data={
            "mapping": json.dumps(mapping),
            "default_account_id": str(refs["account"]["id"]),
            "default_category_id": str(refs["other"]["id"]),
            "dry_run": str(dry_run).lower(),
        },
    )


CSV_BASIC = """date,amount,description,category
2026-08-01,-12.34,Supermarket,Groceries
2026-08-02,-45.00,Dinner,Restaurants
2026-08-03,2500.00,Salary,Salary
"""


def test_dry_run_previews_without_writing(client, refs) -> None:
    body = upload(
        client,
        refs,
        CSV_BASIC,
        {
            "date": "date",
            "amount": "amount",
            "description": "description",
            "category": "category",
        },
    ).json()

    assert body["dry_run"] is True
    assert body["imported"] == 3
    assert len(body["preview"]) == 3
    # Nothing written yet.
    assert client.get("/api/transactions").json()["total"] == 0


def test_real_import_writes_and_matches_categories(client, refs) -> None:
    body = upload(
        client,
        refs,
        CSV_BASIC,
        {
            "date": "date",
            "amount": "amount",
            "description": "description",
            "category": "category",
        },
        dry_run=False,
    ).json()

    assert body["imported"] == 3
    page = client.get("/api/transactions").json()
    assert page["total"] == 3

    by_desc = {t["description"]: t for t in page["items"]}
    assert by_desc["Supermarket"]["category_name"] == "Groceries"
    assert by_desc["Salary"]["amount"] == "2500.00"


def test_unmatched_category_falls_back_to_default(client, refs) -> None:
    csv_text = "date,amount,description,category\n2026-08-01,-9.99,Thing,Nonexistent\n"
    upload(
        client,
        refs,
        csv_text,
        {"date": "date", "amount": "amount", "description": "description", "category": "category"},
        dry_run=False,
    )

    txn = client.get("/api/transactions").json()["items"][0]
    assert txn["category_name"] == "Other expenses"


def test_bad_rows_are_reported_not_swallowed(client, refs) -> None:
    """One broken row must not silently vanish or poison the good ones."""
    csv_text = (
        "date,amount,description\n"
        "2026-08-01,-12.34,Good row\n"
        "not-a-date,-5.00,Bad date\n"
        "2026-08-03,abc,Bad amount\n"
        "2026-08-04,-7.50,Another good row\n"
    )
    body = upload(
        client,
        refs,
        csv_text,
        {"date": "date", "amount": "amount", "description": "description"},
        dry_run=False,
    ).json()

    assert body["imported"] == 2
    assert len(body["errors"]) == 2
    # Row numbers point at the file's own lines, header included.
    assert {e["row"] for e in body["errors"]} == {3, 4}
    assert client.get("/api/transactions").json()["total"] == 2


def test_semicolon_delimited_german_export(client, refs) -> None:
    """A German bank export: semicolons, dd.mm.yyyy, comma decimals."""
    csv_text = (
        "Datum;Betrag;Verwendungszweck\n"
        "01.08.2026;-1.234,56;Miete\n"
        "02.08.2026;2.500,00;Gehalt\n"
    )
    body = upload(
        client,
        refs,
        csv_text,
        {"date": "Datum", "amount": "Betrag", "description": "Verwendungszweck"},
        dry_run=False,
    ).json()

    assert body["imported"] == 2
    assert body["errors"] == []

    amounts = {t["description"]: t["amount"] for t in client.get("/api/transactions").json()["items"]}
    assert amounts["Miete"] == "-1234.56"
    assert amounts["Gehalt"] == "2500.00"


def test_missing_required_mapping_is_rejected(client, refs) -> None:
    body = upload(client, refs, CSV_BASIC, {"description": "description"}).json()
    assert body["imported"] == 0
    assert "required" in body["errors"][0]["message"]


def test_column_detection(client, refs) -> None:
    resp = client.post(
        "/api/reports/columns",
        files={"file": ("bank.csv", b"Datum;Betrag;Text\n", "text/csv")},
    )
    assert resp.status_code == 200
    assert resp.json() == {"columns": ["Datum", "Betrag", "Text"], "delimiter": ";"}


# ----------------------------------------------------------------- reports


def test_month_over_month_comparison(client, refs) -> None:
    add(client, refs, "-100.00", "groceries", "2026-07-10")
    add(client, refs, "-150.00", "groceries", "2026-08-10")
    add(client, refs, "-900.00", "rent", "2026-07-01")

    body = client.get(
        "/api/reports/month-over-month", params={"month": "2026-08-15"}
    ).json()
    by_name = {c["name"]: c for c in body}

    assert Decimal(by_name["Food"]["current"]) == Decimal("150.00")
    assert Decimal(by_name["Food"]["previous"]) == Decimal("100.00")
    assert Decimal(by_name["Food"]["change"]) == Decimal("50.00")
    assert by_name["Food"]["change_percent"] == pytest.approx(50.0)

    # Rent stopped: shown as a full decrease, not omitted.
    assert Decimal(by_name["Housing"]["change"]) == Decimal("-900.00")


def test_change_percent_is_null_when_previous_was_zero(client, refs) -> None:
    """A percentage change from nothing is undefined, not 100%."""
    add(client, refs, "-50.00", "groceries", "2026-08-10")

    body = client.get(
        "/api/reports/month-over-month", params={"month": "2026-08-15"}
    ).json()
    assert body[0]["change_percent"] is None


def test_yearly_summary_and_savings_rate(client, refs) -> None:
    add(client, refs, "3000.00", "salary", "2026-01-31")
    add(client, refs, "3000.00", "salary", "2026-02-28")
    add(client, refs, "-1500.00", "rent", "2026-01-05")
    add(client, refs, "-1500.00", "rent", "2026-02-05")

    body = client.get("/api/reports/yearly", params={"year": 2026}).json()
    assert Decimal(body["income"]) == Decimal("6000.00")
    assert Decimal(body["expenses"]) == Decimal("3000.00")
    assert Decimal(body["net"]) == Decimal("3000.00")
    assert body["savings_rate"] == pytest.approx(50.0)
    assert len(body["months"]) == 12


def test_savings_rate_null_without_income(client, refs) -> None:
    add(client, refs, "-100.00", "groceries", "2026-03-01")
    body = client.get("/api/reports/yearly", params={"year": 2026}).json()
    assert body["savings_rate"] is None
