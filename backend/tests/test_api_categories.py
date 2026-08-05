from __future__ import annotations


def _find(client, name: str) -> dict:
    resp = client.get("/api/categories", params={"include_archived": True})
    return next(c for c in resp.json() if c["name"] == name)


def test_list_and_tree(client) -> None:
    flat = client.get("/api/categories").json()
    assert len(flat) > 30

    tree = client.get("/api/categories/tree", params={"kind": "expense"}).json()
    names = {node["name"] for node in tree}
    assert "Subscriptions" in names
    assert all(node["kind"] == "expense" for node in tree)

    subs = next(n for n in tree if n["name"] == "Subscriptions")
    assert {c["name"] for c in subs["children"]} >= {"Streaming", "Gym"}


def test_create_child_category(client) -> None:
    parent = _find(client, "Subscriptions")
    resp = client.post(
        "/api/categories",
        json={"name": "Newspapers", "kind": "expense", "parent_id": parent["id"]},
    )
    assert resp.status_code == 201
    assert resp.json()["parent_id"] == parent["id"]


def test_rejects_third_level(client) -> None:
    """Two levels is a hard constraint, not a convention."""
    streaming = _find(client, "Streaming")  # already a child
    resp = client.post(
        "/api/categories",
        json={"name": "Netflix", "kind": "expense", "parent_id": streaming["id"]},
    )
    assert resp.status_code == 422
    assert "two levels" in resp.json()["detail"]


def test_rejects_mismatched_kind(client) -> None:
    salary = _find(client, "Salary")  # income
    resp = client.post(
        "/api/categories",
        json={"name": "Bogus", "kind": "expense", "parent_id": salary["id"]},
    )
    assert resp.status_code == 422


def test_rejects_duplicate_name_under_same_parent(client) -> None:
    parent = _find(client, "Food")
    resp = client.post(
        "/api/categories",
        json={"name": "Groceries", "kind": "expense", "parent_id": parent["id"]},
    )
    assert resp.status_code == 409


def test_delete_blocked_when_in_use(client) -> None:
    groceries = _find(client, "Groceries")
    account = client.get("/api/accounts").json()[0]
    client.post(
        "/api/transactions",
        json={
            "date": "2026-08-01",
            "amount": "-25.00",
            "account_id": account["id"],
            "category_id": groceries["id"],
            "description": "Supermarket",
        },
    )

    resp = client.delete(f"/api/categories/{groceries['id']}")
    assert resp.status_code == 409
    assert "archive" in resp.json()["detail"].lower()


def test_delete_blocked_when_it_has_children(client) -> None:
    food = _find(client, "Food")
    assert client.delete(f"/api/categories/{food['id']}").status_code == 409


def test_archive_hides_from_default_list(client) -> None:
    gym = _find(client, "Gym")
    resp = client.patch(f"/api/categories/{gym['id']}", json={"archived": True})
    assert resp.status_code == 200

    visible = {c["name"] for c in client.get("/api/categories").json()}
    assert "Gym" not in visible

    all_names = {
        c["name"]
        for c in client.get("/api/categories", params={"include_archived": True}).json()
    }
    assert "Gym" in all_names
