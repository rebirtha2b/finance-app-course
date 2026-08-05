from __future__ import annotations

from decimal import Decimal

import pytest


@pytest.fixture()
def refs(client) -> dict:
    categories = client.get("/api/categories", params={"include_archived": True}).json()
    by_name = {c["name"]: c for c in categories}
    return {
        "account": client.get("/api/accounts").json()[0],
        "food": by_name["Food"],
        "groceries": by_name["Groceries"],
        "restaurants": by_name["Restaurants"],
        "clothing": by_name["Clothing"],
        "salary": by_name["Salary"],
    }


def spend(client, refs, amount: str, category: str, date: str = "2026-08-10") -> None:
    resp = client.post(
        "/api/transactions",
        json={
            "date": date,
            "amount": amount,
            "account_id": refs["account"]["id"],
            "category_id": refs[category]["id"],
            "description": "test",
        },
    )
    assert resp.status_code == 201, resp.text


def budget(client, refs, category: str, limit: str, **kw) -> dict:
    resp = client.post(
        "/api/budgets",
        json={
            "category_id": refs[category]["id"],
            "limit": limit,
            "start_month": kw.pop("start_month", "2026-01-01"),
            **kw,
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def status(client, month: str = "2026-08-15") -> dict:
    return client.get("/api/budgets/status", params={"month": month}).json()


def test_over_budget_is_flagged(client, refs) -> None:
    """The PRD's acceptance case: €400 budget, €450 spent."""
    budget(client, refs, "clothing", "400.00")
    spend(client, refs, "-450.00", "clothing")

    item = status(client)["items"][0]
    assert item["spent"] == "450.00"
    assert item["limit"] == "400.00"
    assert item["remaining"] == "-50.00"
    assert item["over_budget"] is True
    assert item["percent_used"] == pytest.approx(112.5)


def test_exactly_at_limit_is_not_over(client, refs) -> None:
    """A boundary that is easy to get wrong with >= instead of >."""
    budget(client, refs, "clothing", "400.00")
    spend(client, refs, "-400.00", "clothing")

    item = status(client)["items"][0]
    assert item["remaining"] == "0.00"
    assert item["percent_used"] == pytest.approx(100.0)
    assert item["over_budget"] is False


def test_no_spending(client, refs) -> None:
    budget(client, refs, "clothing", "400.00")
    item = status(client)["items"][0]
    assert item["spent"] == "0.00"
    assert item["remaining"] == "400.00"
    assert item["percent_used"] == 0
    assert item["over_budget"] is False


def test_parent_budget_counts_child_spending(client, refs) -> None:
    """Budgeting "Food" must capture Groceries and Restaurants."""
    budget(client, refs, "food", "500.00")
    spend(client, refs, "-300.00", "groceries")
    spend(client, refs, "-120.00", "restaurants")
    spend(client, refs, "-50.00", "clothing")  # unrelated category

    item = status(client)["items"][0]
    assert item["category_name"] == "Food"
    assert item["spent"] == "420.00"
    assert item["remaining"] == "80.00"


def test_refund_reduces_spend(client, refs) -> None:
    budget(client, refs, "clothing", "400.00")
    spend(client, refs, "-200.00", "clothing")
    spend(client, refs, "50.00", "clothing")  # returned an item

    item = status(client)["items"][0]
    assert item["spent"] == "150.00"
    assert item["remaining"] == "250.00"


def test_only_counts_the_selected_month(client, refs) -> None:
    budget(client, refs, "clothing", "400.00")
    spend(client, refs, "-100.00", "clothing", date="2026-07-31")
    spend(client, refs, "-250.00", "clothing", date="2026-08-01")
    spend(client, refs, "-999.00", "clothing", date="2026-09-01")

    item = status(client, month="2026-08-15")["items"][0]
    assert item["spent"] == "250.00"
    assert item["window_start"] == "2026-08-01"
    assert item["window_end"] == "2026-08-31"


def test_yearly_budget_uses_the_whole_year(client, refs) -> None:
    budget(client, refs, "clothing", "1200.00", period="yearly")
    spend(client, refs, "-300.00", "clothing", date="2026-02-01")
    spend(client, refs, "-400.00", "clothing", date="2026-11-30")
    spend(client, refs, "-999.00", "clothing", date="2025-06-01")  # prior year

    item = status(client, month="2026-08-15")["items"][0]
    assert item["spent"] == "700.00"
    assert item["window_start"] == "2026-01-01"
    assert item["window_end"] == "2026-12-31"


def test_statuses_sorted_most_at_risk_first(client, refs) -> None:
    budget(client, refs, "clothing", "100.00")
    budget(client, refs, "food", "1000.00")
    spend(client, refs, "-90.00", "clothing")  # 90%
    spend(client, refs, "-100.00", "groceries")  # 10%

    names = [i["category_name"] for i in status(client)["items"]]
    assert names == ["Clothing", "Food"]


def test_totals_across_budgets(client, refs) -> None:
    budget(client, refs, "clothing", "100.00")
    budget(client, refs, "food", "400.00")
    spend(client, refs, "-50.00", "clothing")
    spend(client, refs, "-100.00", "groceries")

    body = status(client)
    assert Decimal(body["total_limit"]) == Decimal("500.00")
    assert Decimal(body["total_spent"]) == Decimal("150.00")
    assert Decimal(body["total_remaining"]) == Decimal("350.00")


def test_rollover_carries_unspent_budget(client, refs) -> None:
    budget(client, refs, "clothing", "100.00", start_month="2026-06-01", rollover=True)
    spend(client, refs, "-40.00", "clothing", date="2026-06-15")  # 60 left over
    spend(client, refs, "-30.00", "clothing", date="2026-07-15")  # 70 left over

    item = status(client, month="2026-08-15")["items"][0]
    assert item["rollover"] == "130.00"
    assert item["effective_limit"] == "230.00"
    assert item["remaining"] == "230.00"


def test_rollover_does_not_carry_overspend(client, refs) -> None:
    """A bad month must not shrink the next month's budget."""
    budget(client, refs, "clothing", "100.00", start_month="2026-07-01", rollover=True)
    spend(client, refs, "-500.00", "clothing", date="2026-07-15")

    item = status(client, month="2026-08-15")["items"][0]
    assert item["rollover"] == "0.00"
    assert item["effective_limit"] == "100.00"


def test_rollover_off_by_default(client, refs) -> None:
    budget(client, refs, "clothing", "100.00", start_month="2026-06-01")
    item = status(client, month="2026-08-15")["items"][0]
    assert item["rollover"] == "0.00"
    assert item["effective_limit"] == "100.00"


def test_income_category_rejected(client, refs) -> None:
    resp = client.post(
        "/api/budgets",
        json={"category_id": refs["salary"]["id"], "limit": "100.00"},
    )
    assert resp.status_code == 422


def test_duplicate_budget_rejected(client, refs) -> None:
    budget(client, refs, "clothing", "100.00")
    resp = client.post(
        "/api/budgets",
        json={"category_id": refs["clothing"]["id"], "limit": "200.00"},
    )
    assert resp.status_code == 409


def test_negative_limit_rejected(client, refs) -> None:
    resp = client.post(
        "/api/budgets",
        json={"category_id": refs["clothing"]["id"], "limit": "-100.00"},
    )
    assert resp.status_code == 422


def test_update_and_delete(client, refs) -> None:
    b = budget(client, refs, "clothing", "100.00")

    updated = client.patch(f"/api/budgets/{b['id']}", json={"limit": "250.00"}).json()
    assert updated["limit"] == "250.00"

    assert client.delete(f"/api/budgets/{b['id']}").status_code == 204
    assert status(client)["items"] == []


def test_inactive_budget_excluded_from_status(client, refs) -> None:
    b = budget(client, refs, "clothing", "100.00")
    client.patch(f"/api/budgets/{b['id']}", json={"active": False})
    assert status(client)["items"] == []
