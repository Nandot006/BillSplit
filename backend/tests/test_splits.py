"""Backend Block 10: app/services/splits.compute_bill_splits - the live,
unpersisted per-person breakdown (design.md SS9/SS10)."""

import uuid
from decimal import Decimal

import pytest

from app.models.bill import Bill, BillStatus
from app.models.bill_item import BillItem
from app.models.bill_item_assignment import BillItemAssignment
from app.models.group import Group
from app.models.person import Person
from app.models.user import User
from app.services.splits import compute_bill_splits
from tests.auth_helpers import auth_headers


@pytest.fixture()
def db(db_session_factory):
    session = db_session_factory()
    yield session
    session.close()


@pytest.fixture()
def group_with_two_people(db):
    creator = User(id=uuid.uuid4(), email="creator@example.com")
    db.add(creator)
    db.flush()
    group = Group(name="Dinner", creator_user_id=creator.id)
    db.add(group)
    db.flush()
    alice = Person(group_id=group.id, display_name="Alice")
    bob = Person(group_id=group.id, display_name="Bob")
    db.add_all([alice, bob])
    db.commit()
    return group, alice, bob


def test_tax_and_tip_split_evenly_with_largest_remainder_rounding(db, group_with_two_people):
    group, alice, bob = group_with_two_people
    bill = Bill(
        group_id=group.id,
        status=BillStatus.OPEN,
        tax_total=Decimal("1.01"),
        tip_total=Decimal("0"),
    )
    db.add(bill)
    db.flush()
    db.commit()

    splits = compute_bill_splits(bill, [alice, bob])
    by_name = {s.display_name: s for s in splits}

    # 1.01 / 2 = 0.505 each -> floor to 0.50, one leftover cent. Alice sorts
    # first alphabetically, so she gets it - sums to exactly 1.01.
    assert by_name["Alice"].tax_share == Decimal("0.51")
    assert by_name["Bob"].tax_share == Decimal("0.50")
    assert by_name["Alice"].tax_share + by_name["Bob"].tax_share == Decimal("1.01")


def test_item_subtotal_share_reflects_current_assignments(db, group_with_two_people):
    group, alice, bob = group_with_two_people
    bill = Bill(group_id=group.id, status=BillStatus.OPEN, tax_total=Decimal("0"))
    db.add(bill)
    db.flush()
    solo_item = BillItem(bill_id=bill.id, parsed_name="Burger", price=Decimal("10.00"))
    shared_item = BillItem(bill_id=bill.id, parsed_name="Fries", price=Decimal("5.00"))
    db.add_all([solo_item, shared_item])
    db.flush()
    db.add(
        BillItemAssignment(
            bill_item_id=solo_item.id, person_id=alice.id, is_predicted=False, share_fraction=1.0
        )
    )
    db.add_all(
        [
            BillItemAssignment(
                bill_item_id=shared_item.id,
                person_id=alice.id,
                is_predicted=False,
                share_fraction=0.5,
            ),
            BillItemAssignment(
                bill_item_id=shared_item.id,
                person_id=bob.id,
                is_predicted=False,
                share_fraction=0.5,
            ),
        ]
    )
    db.commit()

    splits = compute_bill_splits(bill, [alice, bob])
    by_name = {s.display_name: s for s in splits}

    assert by_name["Alice"].item_subtotal_share == Decimal("12.50")  # 10.00 + half of 5.00
    assert by_name["Bob"].item_subtotal_share == Decimal("2.50")
    assert by_name["Alice"].total_owed == Decimal("12.50")
    assert by_name["Bob"].total_owed == Decimal("2.50")


def test_person_not_in_current_people_list_is_excluded_from_splits(db, group_with_two_people):
    group, alice, bob = group_with_two_people
    bill = Bill(group_id=group.id, status=BillStatus.OPEN, tax_total=Decimal("0"))
    db.add(bill)
    db.flush()
    item = BillItem(bill_id=bill.id, parsed_name="Burger", price=Decimal("10.00"))
    db.add(item)
    db.flush()
    db.add(
        BillItemAssignment(
            bill_item_id=item.id, person_id=alice.id, is_predicted=False, share_fraction=1.0
        )
    )
    db.commit()

    # Only Bob passed in - Alice's stale assignment (e.g. she was removed
    # from the group without this particular bill being redistributed) is
    # simply skipped rather than raising.
    splits = compute_bill_splits(bill, [bob])
    assert len(splits) == 1
    assert splits[0].display_name == "Bob"
    assert splits[0].item_subtotal_share == Decimal("0.00")


def test_no_people_returns_empty_list(db, group_with_two_people):
    group, alice, bob = group_with_two_people
    bill = Bill(group_id=group.id, status=BillStatus.OPEN, tax_total=Decimal("5.00"))
    db.add(bill)
    db.commit()

    assert compute_bill_splits(bill, []) == []


# --- API-level ---


def test_get_bill_splits_endpoint(client, db_session_factory):
    db = db_session_factory()
    creator = User(id=uuid.uuid4(), email="creator3@example.com")
    db.add(creator)
    db.commit()
    creator_id = creator.id
    db.close()

    headers = auth_headers(creator_id)
    group_id = client.post("/api/v1/groups", json={"name": "Roomies"}, headers=headers).json()["id"]
    alice_id = client.post(
        f"/api/v1/groups/{group_id}/people", json={"display_name": "Alice"}, headers=headers
    ).json()["id"]
    bill_id = client.post(
        f"/api/v1/groups/{group_id}/bills", json={"merchant_name": "Diner"}, headers=headers
    ).json()["id"]
    item_id = client.post(
        f"/api/v1/bills/{bill_id}/items",
        json={"parsed_name": "Burger", "price": "10.00"},
        headers=headers,
    ).json()["id"]
    client.post(f"/api/v1/bills/{bill_id}/finalize-manual-entry", headers=headers)
    client.put(
        f"/api/v1/bills/{bill_id}/items/{item_id}/assign",
        json={"person_id": alice_id},
        headers=headers,
    )
    client.patch(f"/api/v1/bills/{bill_id}", json={"tax_total": "1.00"}, headers=headers)

    resp = client.get(f"/api/v1/bills/{bill_id}/splits", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["person_id"] == alice_id
    assert body[0]["item_subtotal_share"] == "10.00"
    assert body[0]["tax_share"] == "1.00"
    assert body[0]["total_owed"] == "11.00"
