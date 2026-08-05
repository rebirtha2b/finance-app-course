"""The dashboard must never disagree with the pages it summarises."""

from __future__ import annotations

from datetime import date, timedelta
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
        "clothing": by_name["Clothing"],
        "streaming": by_name["Streaming"],
        "salary": by_name["Salary"],
    }


def spend(client, refs, amount: str, category: str, when: date) -> None:
    resp = client.post(
        "/api/transactions",
        json={
            "date": when.isoformat(),
            "amount": amount,
            "account_id": refs["account"]["id"],
            "category_id": refs[category]["id"],
            "description": "test",
        },
    )
    assert resp.status_code == 201, resp.text


def test_empty_dashboard_renders(client) -> None:
    """A brand new install must not error or divide by zero."""
    body = client.get("/api/dashboard").json()
    assert body["net_worth"] == "0.00"
    assert body["this_month"]["net"] == "0.00"
    assert body["spending_by_category"] == []
    assert body["upcoming"] == []
    assert body["portfolio"]["holdings_count"] == 0
    assert len(body["cash_flow"]) == 12


def test_month_kpis_match_transactions_endpoint(client, refs) -> None:
    today = date.today()
    spend(client, refs, "2500.00", "salary", today)
    spend(client, refs, "-900.00", "rent", today)
    spend(client, refs, "-120.00", "groceries", today)

    body = client.get("/api/dashboard").json()
    first = today.replace(day=1)
    page = client.get(
        "/api/transactions", params={"from": first.isoformat(), "to": today.isoformat()}
    ).json()

    # Same numbers, computed independently by two endpoints.
    assert body["this_month"]["income"] == page["totals"]["income"]
    assert body["this_month"]["expenses"] == page["totals"]["expenses"]
    assert body["this_month"]["net"] == page["totals"]["net"]


def test_net_worth_includes_cash_and_portfolio(client, refs, fake_prices) -> None:
    today = date.today()
    spend(client, refs, "1000.00", "salary", today)

    fake_prices.add_security("SAP.DE", currency="EUR", price="100.00")
    client.post("/api/holdings", json={"ticker": "SAP.DE", "quantity": "5"})

    body = client.get("/api/dashboard").json()
    assert Decimal(body["cash_total"]) == Decimal("1000.00")
    assert Decimal(body["portfolio"]["total_value"]) == Decimal("500.00")
    assert Decimal(body["net_worth"]) == Decimal("1500.00")


def test_spending_rolls_children_into_parent(client, refs) -> None:
    today = date.today()
    spend(client, refs, "-300.00", "groceries", today)
    spend(client, refs, "-120.00", "restaurants", today)
    spend(client, refs, "-900.00", "rent", today)

    body = client.get("/api/dashboard").json()
    by_name = {c["name"]: c for c in body["spending_by_category"]}

    # Groceries + Restaurants appear as one "Food" slice.
    assert Decimal(by_name["Food"]["amount"]) == Decimal("420.00")
    assert Decimal(by_name["Housing"]["amount"]) == Decimal("900.00")
    assert by_name["Housing"]["percent"] == pytest.approx(68.2, abs=0.1)

    # Sorted biggest first.
    assert body["spending_by_category"][0]["name"] == "Housing"


def test_spending_excludes_income(client, refs) -> None:
    today = date.today()
    spend(client, refs, "2500.00", "salary", today)
    spend(client, refs, "-100.00", "groceries", today)

    body = client.get("/api/dashboard").json()
    names = {c["name"] for c in body["spending_by_category"]}
    assert names == {"Food"}


def test_cash_flow_series_covers_12_months_with_gaps(client, refs) -> None:
    today = date.today()
    spend(client, refs, "-50.00", "groceries", today)

    body = client.get("/api/dashboard").json()
    series = body["cash_flow"]

    assert len(series) == 12
    # Oldest first, ending with the current month.
    assert series[-1]["month"] == today.replace(day=1).isoformat()
    assert Decimal(series[-1]["expenses"]) == Decimal("50.00")
    # Empty months are present as zeros, not omitted.
    assert Decimal(series[0]["income"]) == Decimal("0.00")


def test_budgets_at_risk_only_shows_the_urgent_ones(client, refs) -> None:
    today = date.today()
    first = today.replace(day=1).isoformat()

    for category, limit in [("clothing", "100.00"), ("groceries", "1000.00")]:
        client.post(
            "/api/budgets",
            json={
                "category_id": refs[category]["id"],
                "limit": limit,
                "start_month": first,
            },
        )

    spend(client, refs, "-95.00", "clothing", today)  # 95% — at risk
    spend(client, refs, "-50.00", "groceries", today)  # 5% — fine

    body = client.get("/api/dashboard").json()
    assert [b["category_name"] for b in body["budgets_at_risk"]] == ["Clothing"]


def test_upcoming_charges_within_14_days(client, refs) -> None:
    today = date.today()
    soon = today + timedelta(days=5)
    far = today + timedelta(days=40)

    client.post(
        "/api/recurring",
        json={
            "name": "Netflix",
            "amount": "-12.99",
            "category_id": refs["streaming"]["id"],
            "account_id": refs["account"]["id"],
            "frequency": "monthly",
            "day_of_month": soon.day,
            "start_date": soon.isoformat(),
        },
    )
    client.post(
        "/api/recurring",
        json={
            "name": "Faraway",
            "amount": "-99.00",
            "category_id": refs["streaming"]["id"],
            "account_id": refs["account"]["id"],
            "frequency": "yearly",
            "start_date": far.isoformat(),
        },
    )

    body = client.get("/api/dashboard").json()
    names = [u["name"] for u in body["upcoming"]]
    assert "Netflix" in names
    assert "Faraway" not in names

    netflix = next(u for u in body["upcoming"] if u["name"] == "Netflix")
    assert 0 <= netflix["days_away"] <= 14
