from __future__ import annotations

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
        "food": by_name["Food"],
        "rent": by_name["Rent"],
        "salary": by_name["Salary"],
    }


def add(client, refs, *, amount: str, category: str, date="2026-08-01", desc="") -> dict:
    resp = client.post(
        "/api/transactions",
        json={
            "date": date,
            "amount": amount,
            "account_id": refs["account"]["id"],
            "category_id": refs[category]["id"],
            "description": desc,
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_create_and_read_back_exact_amount(client, refs) -> None:
    created = add(client, refs, amount="-12.34", category="groceries", desc="Lidl")
    assert created["amount"] == "-12.34"
    assert created["category_name"] == "Groceries"
    assert created["account_name"] == "Main account"

    fetched = client.get(f"/api/transactions/{created['id']}").json()
    assert Decimal(fetched["amount"]) == Decimal("-12.34")


def test_amount_is_serialised_as_string_not_float(client, refs) -> None:
    """A JSON number would be a double in the browser and lose precision."""
    add(client, refs, amount="-0.10", category="groceries")
    raw = client.get("/api/transactions").text
    assert '"amount":"-0.10"' in raw


def test_zero_amount_rejected(client, refs) -> None:
    resp = client.post(
        "/api/transactions",
        json={
            "date": "2026-08-01",
            "amount": "0",
            "account_id": refs["account"]["id"],
            "category_id": refs["groceries"]["id"],
        },
    )
    assert resp.status_code == 422


def test_unknown_category_rejected(client, refs) -> None:
    resp = client.post(
        "/api/transactions",
        json={
            "date": "2026-08-01",
            "amount": "-5",
            "account_id": refs["account"]["id"],
            "category_id": 999999,
        },
    )
    assert resp.status_code == 404


def test_totals_reflect_filter_not_page(client, refs) -> None:
    add(client, refs, amount="2500.00", category="salary", date="2026-08-01")
    add(client, refs, amount="-900.00", category="rent", date="2026-08-02")
    add(client, refs, amount="-50.00", category="groceries", date="2026-08-03")
    add(client, refs, amount="-30.00", category="restaurants", date="2026-08-04")

    body = client.get("/api/transactions", params={"limit": 1}).json()
    assert len(body["items"]) == 1  # one row on the page...
    assert body["total"] == 4
    # ...but the totals describe all four.
    assert Decimal(body["totals"]["income"]) == Decimal("2500.00")
    assert Decimal(body["totals"]["expenses"]) == Decimal("980.00")
    assert Decimal(body["totals"]["net"]) == Decimal("1520.00")


def test_parent_category_filter_includes_children(client, refs) -> None:
    """Filtering on "Food" must include Groceries and Restaurants."""
    add(client, refs, amount="-50.00", category="groceries")
    add(client, refs, amount="-30.00", category="restaurants")
    add(client, refs, amount="-900.00", category="rent")

    body = client.get(
        "/api/transactions", params={"category_id": refs["food"]["id"]}
    ).json()
    assert body["total"] == 2
    assert Decimal(body["totals"]["expenses"]) == Decimal("80.00")


def test_date_range_filter_is_inclusive(client, refs) -> None:
    add(client, refs, amount="-10.00", category="groceries", date="2026-07-31")
    add(client, refs, amount="-20.00", category="groceries", date="2026-08-01")
    add(client, refs, amount="-40.00", category="groceries", date="2026-08-31")
    add(client, refs, amount="-80.00", category="groceries", date="2026-09-01")

    body = client.get(
        "/api/transactions", params={"from": "2026-08-01", "to": "2026-08-31"}
    ).json()
    assert body["total"] == 2
    assert Decimal(body["totals"]["expenses"]) == Decimal("60.00")


def test_text_search_matches_description_and_notes(client, refs) -> None:
    add(client, refs, amount="-9.99", category="groceries", desc="Weekly shop")
    client.post(
        "/api/transactions",
        json={
            "date": "2026-08-02",
            "amount": "-4.50",
            "account_id": refs["account"]["id"],
            "category_id": refs["groceries"]["id"],
            "description": "Corner store",
            "notes": "emergency milk",
        },
    )

    assert client.get("/api/transactions", params={"q": "weekly"}).json()["total"] == 1
    assert client.get("/api/transactions", params={"q": "milk"}).json()["total"] == 1
    assert client.get("/api/transactions", params={"q": "zzz"}).json()["total"] == 0


def test_sorting_by_amount(client, refs) -> None:
    add(client, refs, amount="-10.00", category="groceries")
    add(client, refs, amount="-99.00", category="groceries")
    add(client, refs, amount="-50.00", category="groceries")

    asc = client.get(
        "/api/transactions", params={"sort": "amount", "order": "asc"}
    ).json()["items"]
    assert [i["amount"] for i in asc] == ["-99.00", "-50.00", "-10.00"]


def test_pagination_is_stable_across_pages(client, refs) -> None:
    """Same date on every row — the id tiebreaker must prevent repeats."""
    for i in range(10):
        add(client, refs, amount=f"-{i + 1}.00", category="groceries", date="2026-08-01")

    first = client.get("/api/transactions", params={"limit": 5, "offset": 0}).json()
    second = client.get("/api/transactions", params={"limit": 5, "offset": 5}).json()
    ids = [i["id"] for i in first["items"]] + [i["id"] for i in second["items"]]
    assert len(set(ids)) == 10


def test_update_and_delete(client, refs) -> None:
    txn = add(client, refs, amount="-12.00", category="groceries", desc="typo")

    updated = client.patch(
        f"/api/transactions/{txn['id']}",
        json={"amount": "-15.50", "description": "Fixed"},
    ).json()
    assert updated["amount"] == "-15.50"
    assert updated["description"] == "Fixed"
    assert updated["date"] == txn["date"]  # untouched fields survive

    assert client.delete(f"/api/transactions/{txn['id']}").status_code == 204
    assert client.get(f"/api/transactions/{txn['id']}").status_code == 404


def test_refund_recorded_as_positive_on_expense_category(client, refs) -> None:
    """The sign is the client's to choose, which is what makes refunds work."""
    add(client, refs, amount="-80.00", category="groceries", desc="Big shop")
    add(client, refs, amount="20.00", category="groceries", desc="Returned items")

    body = client.get(
        "/api/transactions", params={"category_id": refs["groceries"]["id"]}
    ).json()
    assert Decimal(body["totals"]["net"]) == Decimal("-60.00")
