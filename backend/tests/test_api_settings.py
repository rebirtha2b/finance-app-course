"""Reset is the only irreversible action in the app.

These tests are mostly about what must NOT happen: no deletion without the
exact phrase, and no scope reaching beyond what was asked for.
"""

from __future__ import annotations

import pytest

PHRASE = "DELETE MY DATA"


@pytest.fixture()
def refs(client) -> dict:
    categories = client.get("/api/categories", params={"include_archived": True}).json()
    by_name = {c["name"]: c for c in categories}
    return {
        "account": client.get("/api/accounts").json()[0],
        "groceries": by_name["Groceries"],
        "streaming": by_name["Streaming"],
        "clothing": by_name["Clothing"],
    }


@pytest.fixture()
def populated(client, refs, fake_prices) -> dict:
    client.post(
        "/api/transactions",
        json={
            "date": "2026-08-01",
            "amount": "-42.50",
            "account_id": refs["account"]["id"],
            "category_id": refs["groceries"]["id"],
            "description": "Supermarket",
        },
    )
    client.post(
        "/api/recurring",
        json={
            "name": "Netflix",
            "amount": "-12.99",
            "category_id": refs["streaming"]["id"],
            "account_id": refs["account"]["id"],
            "frequency": "monthly",
            "start_date": "2026-08-01",
        },
    )
    client.post(
        "/api/budgets",
        json={"category_id": refs["clothing"]["id"], "limit": "100.00"},
    )
    fake_prices.add_security("SAP.DE", currency="EUR", price="100.00")
    client.post("/api/holdings", json={"ticker": "SAP.DE", "quantity": "5"})
    return refs


def summary(client) -> dict:
    return client.get("/api/settings/data-summary").json()


def test_summary_reports_what_is_stored(client, populated) -> None:
    s = summary(client)
    assert s["transactions"] >= 1
    assert s["recurring_rules"] == 1
    assert s["budgets"] == 1
    assert s["holdings"] == 1
    assert s["categories"] > 30
    assert s["accounts"] == 1


def test_wrong_phrase_deletes_nothing(client, populated) -> None:
    before = summary(client)

    for wrong in ["", "delete my data", "DELETE", "DELETE MY DATA ", "yes"]:
        resp = client.post(
            "/api/settings/reset", json={"scopes": ["transactions"], "confirm": wrong}
        )
        assert resp.status_code == 400, f"{wrong!r} was accepted"
        assert "Nothing was deleted" in resp.json()["detail"]

    assert summary(client) == before


def test_unknown_scope_deletes_nothing(client, populated) -> None:
    before = summary(client)
    resp = client.post(
        "/api/settings/reset", json={"scopes": ["everything"], "confirm": PHRASE}
    )
    assert resp.status_code == 422
    assert summary(client) == before


def test_empty_scope_list_rejected(client, populated) -> None:
    before = summary(client)
    resp = client.post("/api/settings/reset", json={"scopes": [], "confirm": PHRASE})
    assert resp.status_code == 422
    assert summary(client) == before


def test_transactions_scope_leaves_everything_else(client, populated) -> None:
    """The core guarantee: a scope must not reach beyond itself."""
    resp = client.post(
        "/api/settings/reset", json={"scopes": ["transactions"], "confirm": PHRASE}
    )
    assert resp.status_code == 200

    s = summary(client)
    assert s["transactions"] == 0
    assert s["recurring_rules"] == 1
    assert s["budgets"] == 1
    assert s["holdings"] == 1
    assert s["categories"] > 30


def test_portfolio_scope_leaves_cash_flow(client, populated) -> None:
    client.post(
        "/api/settings/reset", json={"scopes": ["portfolio"], "confirm": PHRASE}
    )

    s = summary(client)
    assert s["holdings"] == 0
    assert s["securities"] == 0
    assert s["price_snapshots"] == 0
    assert s["transactions"] >= 1
    assert s["budgets"] == 1


def test_deleting_rules_keeps_their_transactions(client, populated) -> None:
    """Generated charges record money that actually moved — they survive."""
    client.post("/api/recurring/generate", params={"until": "2026-08-31"})
    before = summary(client)["transactions"]
    assert before >= 2

    client.post("/api/settings/reset", json={"scopes": ["recurring"], "confirm": PHRASE})

    s = summary(client)
    assert s["recurring_rules"] == 0
    assert s["transactions"] == before
    # Detached from the deleted rule rather than removed with it.
    assert all(
        t["recurring_rule_id"] is None
        for t in client.get("/api/transactions").json()["items"]
    )


def test_categories_scope_implies_the_things_that_reference_them(
    client, populated
) -> None:
    """Clearing categories would orphan transactions, so it clears those too."""
    body = client.post(
        "/api/settings/reset", json={"scopes": ["categories"], "confirm": PHRASE}
    ).json()

    assert set(body["scopes"]) >= {"categories", "transactions", "recurring", "budgets"}

    s = summary(client)
    assert s["transactions"] == 0
    assert s["recurring_rules"] == 0
    assert s["budgets"] == 0
    # Defaults come back, or the app would be unusable.
    assert s["categories"] > 30
    assert s["accounts"] == 1
    assert body["categories_restored"] > 30


def test_full_reset_leaves_a_usable_app(client, populated) -> None:
    client.post(
        "/api/settings/reset",
        json={
            "scopes": ["transactions", "recurring", "budgets", "portfolio", "categories"],
            "confirm": PHRASE,
        },
    )

    s = summary(client)
    assert s["transactions"] == 0
    assert s["holdings"] == 0
    assert s["budgets"] == 0
    assert s["categories"] > 30
    assert s["accounts"] == 1

    # And a transaction can be entered immediately afterwards.
    categories = client.get("/api/categories").json()
    account = client.get("/api/accounts").json()[0]
    resp = client.post(
        "/api/transactions",
        json={
            "date": "2026-08-01",
            "amount": "-10.00",
            "account_id": account["id"],
            "category_id": categories[0]["id"],
            "description": "After reset",
        },
    )
    assert resp.status_code == 201


def test_reset_reports_what_it_deleted(client, populated) -> None:
    body = client.post(
        "/api/settings/reset",
        json={"scopes": ["transactions", "portfolio"], "confirm": PHRASE},
    ).json()

    assert body["deleted"]["transactions"] >= 1
    assert body["deleted"]["holdings"] == 1


def test_reset_on_empty_database_is_harmless(client) -> None:
    body = client.post(
        "/api/settings/reset", json={"scopes": ["transactions"], "confirm": PHRASE}
    ).json()
    assert body["deleted"] == {}
