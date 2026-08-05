from __future__ import annotations

from datetime import date
from decimal import Decimal


def test_lookup_validates_ticker(client, fake_prices) -> None:
    fake_prices.add_security("AAPL", name="Apple Inc.", currency="USD")

    body = client.get("/api/securities/lookup", params={"ticker": "aapl"}).json()
    assert body["ticker"] == "AAPL"
    assert body["name"] == "Apple Inc."
    assert body["currency"] == "USD"


def test_lookup_rejects_unknown_ticker(client, fake_prices) -> None:
    """A typo must fail loudly here, not become a holding that never prices."""
    resp = client.get("/api/securities/lookup", params={"ticker": "NOTREAL"})
    assert resp.status_code == 404
    assert "SAP.DE" in resp.json()["detail"]  # the hint about EU suffixes


def test_create_holding_resolves_metadata(client, fake_prices) -> None:
    fake_prices.add_security(
        "SAP.DE", name="SAP SE", currency="EUR", exchange="GER", price="167.38"
    )

    resp = client.post("/api/holdings", json={"ticker": "sap.de", "quantity": "10"})
    assert resp.status_code == 201, resp.text

    body = resp.json()
    assert body["ticker"] == "SAP.DE"
    assert body["name"] == "SAP SE"
    assert body["currency"] == "EUR"
    # Priced immediately rather than blank until the next scheduled refresh.
    assert body["price"] == "167.38"
    assert body["value_base"] == "1673.80"


def test_create_holding_with_unknown_ticker_fails(client, fake_prices) -> None:
    resp = client.post("/api/holdings", json={"ticker": "NOPE", "quantity": "10"})
    assert resp.status_code == 404


def test_duplicate_holding_rejected(client, fake_prices) -> None:
    fake_prices.add_security("SAP.DE", currency="EUR", price="100.00")
    client.post("/api/holdings", json={"ticker": "SAP.DE", "quantity": "10"})

    resp = client.post("/api/holdings", json={"ticker": "SAP.DE", "quantity": "5"})
    assert resp.status_code == 409
    assert "edit the quantity" in resp.json()["detail"]


def test_negative_quantity_rejected(client, fake_prices) -> None:
    fake_prices.add_security("SAP.DE", currency="EUR", price="100.00")
    resp = client.post("/api/holdings", json={"ticker": "SAP.DE", "quantity": "-5"})
    assert resp.status_code == 422


def test_portfolio_totals_across_currencies(client, fake_prices) -> None:
    fake_prices.add_security("SAP.DE", currency="EUR", price="100.00")
    fake_prices.add_security("AAPL", currency="USD", price="200.00")
    fake_prices.set_fx("EUR", "USD", "1.25")

    client.post("/api/holdings", json={"ticker": "SAP.DE", "quantity": "10"})
    client.post("/api/holdings", json={"ticker": "AAPL", "quantity": "10"})

    body = client.get("/api/portfolio").json()
    # €1000 + ($2000 / 1.25 = €1600)
    assert Decimal(body["total_value_base"]) == Decimal("2600.00")
    assert body["base_currency"] == "EUR"
    assert body["has_stale_prices"] is False


def test_portfolio_reports_gain(client, fake_prices) -> None:
    fake_prices.add_security("SAP.DE", currency="EUR", price="150.00")
    client.post(
        "/api/holdings",
        json={"ticker": "SAP.DE", "quantity": "10", "avg_cost_price": "100.00"},
    )

    body = client.get("/api/portfolio").json()
    assert Decimal(body["total_cost_base"]) == Decimal("1000.00")
    assert Decimal(body["total_gain_base"]) == Decimal("500.00")
    assert body["total_gain_percent"] == 50.0


def test_refresh_reports_failures_without_erroring(client, fake_prices) -> None:
    fake_prices.add_security("SAP.DE", currency="EUR", price="100.00")
    client.post("/api/holdings", json={"ticker": "SAP.DE", "quantity": "10"})

    fake_prices.omit = {"SAP.DE"}
    body = client.post("/api/portfolio/refresh").json()

    # A failed fetch is reported, not raised — the page must still render.
    assert body["ok"] is False
    assert body["failed_tickers"] == ["SAP.DE"]

    portfolio = client.get("/api/portfolio").json()
    assert Decimal(portfolio["total_value_base"]) == Decimal("1000.00")


def test_outage_still_returns_a_usable_portfolio(client, fake_prices) -> None:
    fake_prices.add_security("SAP.DE", currency="EUR", price="100.00")
    client.post("/api/holdings", json={"ticker": "SAP.DE", "quantity": "10"})

    fake_prices.raise_on_calls = True
    assert client.post("/api/portfolio/refresh").status_code == 200

    body = client.get("/api/portfolio").json()
    assert Decimal(body["total_value_base"]) == Decimal("1000.00")


def test_update_quantity(client, fake_prices) -> None:
    fake_prices.add_security("SAP.DE", currency="EUR", price="100.00")
    created = client.post(
        "/api/holdings", json={"ticker": "SAP.DE", "quantity": "10"}
    ).json()

    updated = client.patch(
        f"/api/holdings/{created['holding_id']}", json={"quantity": "25"}
    ).json()
    assert updated["quantity"] == "25"
    assert updated["value_base"] == "2500.00"


def test_delete_holding(client, fake_prices) -> None:
    fake_prices.add_security("SAP.DE", currency="EUR", price="100.00")
    created = client.post(
        "/api/holdings", json={"ticker": "SAP.DE", "quantity": "10"}
    ).json()

    assert client.delete(f"/api/holdings/{created['holding_id']}").status_code == 204
    assert client.get("/api/portfolio").json()["holdings"] == []


def test_history_endpoint(client, fake_prices) -> None:
    fake_prices.add_security("SAP.DE", currency="EUR", price="100.00")
    client.post("/api/holdings", json={"ticker": "SAP.DE", "quantity": "10"})
    client.post("/api/portfolio/refresh")

    history = client.get("/api/portfolio/history").json()
    assert len(history) == 1
    assert Decimal(history[0]["total_value"]) == Decimal("1000.00")
    assert history[0]["date"] == date.today().isoformat()
