import uuid

import pytest

from app.models.user import User
from tests.auth_helpers import auth_headers


@pytest.fixture()
def creator_with_group(client, db_session_factory):
    db = db_session_factory()
    creator = User(id=uuid.uuid4(), email="creator@example.com")
    outsider = User(id=uuid.uuid4(), email="outsider@example.com")
    db.add_all([creator, outsider])
    db.commit()
    creator_id, outsider_id = creator.id, outsider.id
    db.close()

    group_resp = client.post(
        "/api/v1/groups", json={"name": "Dinner Crew"}, headers=auth_headers(creator_id)
    )
    return {
        "creator_id": creator_id,
        "outsider_id": outsider_id,
        "group_id": group_resp.json()["id"],
    }


def test_create_bill_without_image_starts_needs_manual_entry(client, creator_with_group):
    resp = client.post(
        f"/api/v1/groups/{creator_with_group['group_id']}/bills",
        json={"merchant_name": "Pasta Place"},
        headers=auth_headers(creator_with_group["creator_id"]),
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "needs_manual_entry"
    assert body["merchant_name"] == "Pasta Place"


def test_create_bill_with_image_starts_processing(client, creator_with_group):
    resp = client.post(
        f"/api/v1/groups/{creator_with_group['group_id']}/bills",
        json={"image_storage_path": "receipts/abc.jpg"},
        headers=auth_headers(creator_with_group["creator_id"]),
    )
    assert resp.json()["status"] == "processing"


def test_outsider_cannot_create_bill_in_groups_they_are_not_in(client, creator_with_group):
    resp = client.post(
        f"/api/v1/groups/{creator_with_group['group_id']}/bills",
        json={},
        headers=auth_headers(creator_with_group["outsider_id"]),
    )
    assert resp.status_code == 404


def _create_manual_bill(client, creator_with_group):
    resp = client.post(
        f"/api/v1/groups/{creator_with_group['group_id']}/bills",
        json={"merchant_name": "Pasta Place"},
        headers=auth_headers(creator_with_group["creator_id"]),
    )
    return resp.json()["id"]


def test_add_items_and_recompute_totals(client, creator_with_group):
    bill_id = _create_manual_bill(client, creator_with_group)
    headers = auth_headers(creator_with_group["creator_id"])

    item1 = client.post(
        f"/api/v1/bills/{bill_id}/items",
        json={
            "parsed_name": "Margherita Pizza",
            "price": "12.50",
            "quantity": 1,
            "base_type": "entree",
        },
        headers=headers,
    )
    assert item1.status_code == 201
    assert item1.json()["parsed_name"] == "Margherita Pizza"

    client.post(
        f"/api/v1/bills/{bill_id}/items",
        json={
            "parsed_name": "Garlic Bread",
            "price": "5.00",
            "quantity": 2,
            "base_type": "side",
            "flavor_tags": ["savory"],
            "dietary_flags": ["vegetarian"],
        },
        headers=headers,
    )

    bill_resp = client.get(f"/api/v1/bills/{bill_id}", headers=headers)
    body = bill_resp.json()
    assert len(body["items"]) == 2
    assert body["subtotal"] == "22.50"  # 12.50*1 + 5.00*2
    assert body["grand_total"] == "22.50"  # no tax/tip set yet

    garlic_bread = next(i for i in body["items"] if i["parsed_name"] == "Garlic Bread")
    assert garlic_bread["flavor_tags"] == ["savory"]
    assert garlic_bread["dietary_flags"] == ["vegetarian"]


def test_update_bill_tax_and_tip_recomputes_grand_total(client, creator_with_group):
    bill_id = _create_manual_bill(client, creator_with_group)
    headers = auth_headers(creator_with_group["creator_id"])
    client.post(
        f"/api/v1/bills/{bill_id}/items",
        json={"parsed_name": "Pizza", "price": "20.00", "quantity": 1},
        headers=headers,
    )

    resp = client.patch(
        f"/api/v1/bills/{bill_id}", json={"tax_total": "2.00", "tip_total": "4.00"}, headers=headers
    )
    assert resp.status_code == 200
    assert resp.json()["grand_total"] == "26.00"


def test_finalize_requires_at_least_one_item(client, creator_with_group):
    bill_id = _create_manual_bill(client, creator_with_group)
    headers = auth_headers(creator_with_group["creator_id"])

    resp = client.post(f"/api/v1/bills/{bill_id}/finalize-manual-entry", headers=headers)
    assert resp.status_code == 422

    client.post(
        f"/api/v1/bills/{bill_id}/items",
        json={"parsed_name": "Pizza", "price": "20.00"},
        headers=headers,
    )
    resp = client.post(f"/api/v1/bills/{bill_id}/finalize-manual-entry", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "needs_review"


def test_cannot_add_items_after_finalizing(client, creator_with_group):
    bill_id = _create_manual_bill(client, creator_with_group)
    headers = auth_headers(creator_with_group["creator_id"])
    client.post(
        f"/api/v1/bills/{bill_id}/items",
        json={"parsed_name": "Pizza", "price": "20.00"},
        headers=headers,
    )
    client.post(f"/api/v1/bills/{bill_id}/finalize-manual-entry", headers=headers)

    resp = client.post(
        f"/api/v1/bills/{bill_id}/items",
        json={"parsed_name": "Late Item", "price": "1.00"},
        headers=headers,
    )
    assert resp.status_code == 409


def test_delete_item_recomputes_totals(client, creator_with_group):
    bill_id = _create_manual_bill(client, creator_with_group)
    headers = auth_headers(creator_with_group["creator_id"])
    item_resp = client.post(
        f"/api/v1/bills/{bill_id}/items",
        json={"parsed_name": "Pizza", "price": "20.00"},
        headers=headers,
    )
    item_id = item_resp.json()["id"]

    delete_resp = client.delete(f"/api/v1/bills/{bill_id}/items/{item_id}", headers=headers)
    assert delete_resp.status_code == 204

    bill_resp = client.get(f"/api/v1/bills/{bill_id}", headers=headers)
    assert bill_resp.json()["items"] == []
    assert bill_resp.json()["subtotal"] == "0.00"


def test_outsider_cannot_view_bill(client, creator_with_group):
    bill_id = _create_manual_bill(client, creator_with_group)
    resp = client.get(
        f"/api/v1/bills/{bill_id}", headers=auth_headers(creator_with_group["outsider_id"])
    )
    assert resp.status_code == 404
