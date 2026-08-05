from __future__ import annotations

from decimal import Decimal

import pytest


@pytest.fixture()
def refs(client) -> dict:
    categories = client.get("/api/categories", params={"include_archived": True}).json()
    by_name = {c["name"]: c for c in categories}
    return {
        "account": client.get("/api/accounts").json()[0],
        "rent": by_name["Rent"],
        "streaming": by_name["Streaming"],
        "gym": by_name["Gym"],
        "salary": by_name["Salary"],
    }


def make(client, refs, *, category="streaming", amount="-12.99", **overrides) -> dict:
    body = {
        "name": overrides.pop("name", "Netflix"),
        "amount": amount,
        "category_id": refs[category]["id"],
        "account_id": refs["account"]["id"],
        "description": overrides.pop("description", ""),
        "frequency": overrides.pop("frequency", "monthly"),
        "start_date": overrides.pop("start_date", "2026-01-01"),
        **overrides,
    }
    resp = client.post("/api/recurring", json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_create_returns_derived_fields(client, refs) -> None:
    rule = make(client, refs, amount="-12.99")
    assert rule["amount"] == "-12.99"
    assert rule["monthly_equivalent"] == "12.99"  # positive: it's a cost
    assert rule["category_name"] == "Streaming"
    assert rule["next_due_date"] is not None


def test_zero_amount_rejected(client, refs) -> None:
    resp = client.post(
        "/api/recurring",
        json={
            "name": "Bad",
            "amount": "0",
            "category_id": refs["streaming"]["id"],
            "account_id": refs["account"]["id"],
            "frequency": "monthly",
            "start_date": "2026-01-01",
        },
    )
    assert resp.status_code == 422


def test_end_before_start_rejected(client, refs) -> None:
    resp = client.post(
        "/api/recurring",
        json={
            "name": "Bad",
            "amount": "-5",
            "category_id": refs["streaming"]["id"],
            "account_id": refs["account"]["id"],
            "frequency": "monthly",
            "start_date": "2026-06-01",
            "end_date": "2026-01-01",
        },
    )
    assert resp.status_code == 422


def test_generate_endpoint_is_idempotent(client, refs) -> None:
    make(client, refs, start_date="2026-05-01")

    first = client.post("/api/recurring/generate", params={"until": "2026-07-15"}).json()
    second = client.post("/api/recurring/generate", params={"until": "2026-07-15"}).json()

    assert first["created"] == 3
    assert second["created"] == 0
    assert client.get("/api/transactions").json()["total"] == 3


def test_generated_transactions_are_flagged(client, refs) -> None:
    rule = make(client, refs, start_date="2026-05-01")
    client.post("/api/recurring/generate", params={"until": "2026-05-31"})

    txn = client.get("/api/transactions").json()["items"][0]
    assert txn["recurring_rule_id"] == rule["id"]
    assert txn["due_date"] == "2026-05-01"


def test_subscriptions_normalises_to_monthly(client, refs) -> None:
    make(client, refs, name="Netflix", amount="-12.00", frequency="monthly")
    make(client, refs, name="Gym", category="gym", amount="-360.00", frequency="yearly")
    make(client, refs, name="Rent", category="rent", amount="-900.00", frequency="monthly")

    body = client.get("/api/subscriptions").json()
    by_name = {i["name"]: i for i in body["items"]}

    assert by_name["Netflix"]["monthly_equivalent"] == "12.00"
    assert by_name["Gym"]["monthly_equivalent"] == "30.00"  # 360/12
    assert by_name["Rent"]["monthly_equivalent"] == "900.00"

    assert Decimal(body["total_monthly"]) == Decimal("942.00")
    assert Decimal(body["total_annual"]) == Decimal("11304.00")

    # Sorted by monthly cost descending, so the thing worth cancelling is at
    # the top — the yearly gym (€30/mo) outranks Netflix (€12/mo) even though
    # its per-charge amount is much larger and less frequent.
    assert [i["name"] for i in body["items"]] == ["Rent", "Gym", "Netflix"]


def test_subscriptions_excludes_income_and_paused(client, refs) -> None:
    make(client, refs, name="Netflix", amount="-12.00")
    make(client, refs, name="Salary", category="salary", amount="2500.00")
    paused = make(client, refs, name="Old gym", category="gym", amount="-40.00")
    client.patch(f"/api/recurring/{paused['id']}", json={"active": False})

    body = client.get("/api/subscriptions").json()
    assert [i["name"] for i in body["items"]] == ["Netflix"]
    assert Decimal(body["total_monthly"]) == Decimal("12.00")


def test_pause_stops_generation(client, refs) -> None:
    rule = make(client, refs, start_date="2026-05-01")
    client.post("/api/recurring/generate", params={"until": "2026-05-31"})
    assert client.get("/api/transactions").json()["total"] == 1

    client.patch(f"/api/recurring/{rule['id']}", json={"active": False})
    client.post("/api/recurring/generate", params={"until": "2026-08-31"})
    assert client.get("/api/transactions").json()["total"] == 1


def test_amount_change_does_not_rewrite_history(client, refs) -> None:
    """A price rise applies going forward, not retroactively."""
    rule = make(client, refs, amount="-12.00", start_date="2026-05-01")
    client.post("/api/recurring/generate", params={"until": "2026-06-30"})

    client.patch(f"/api/recurring/{rule['id']}", json={"amount": "-15.00"})
    client.post("/api/recurring/generate", params={"until": "2026-07-31"})

    amounts = sorted(i["amount"] for i in client.get("/api/transactions").json()["items"])
    assert amounts == ["-12.00", "-12.00", "-15.00"]


def test_delete_keeps_history_by_default(client, refs) -> None:
    rule = make(client, refs, start_date="2026-05-01")
    client.post("/api/recurring/generate", params={"until": "2026-06-30"})

    assert client.delete(f"/api/recurring/{rule['id']}").status_code == 204

    page = client.get("/api/transactions").json()
    assert page["total"] == 2
    # Detached from the deleted rule, but the money still moved.
    assert all(i["recurring_rule_id"] is None for i in page["items"])


def test_delete_can_remove_history_too(client, refs) -> None:
    rule = make(client, refs, start_date="2026-05-01")
    client.post("/api/recurring/generate", params={"until": "2026-06-30"})

    client.delete(
        f"/api/recurring/{rule['id']}", params={"delete_transactions": True}
    )
    assert client.get("/api/transactions").json()["total"] == 0
