"""Backend Block 12: app/services/settlement (sync_bill_splits,
ensure_settlement_rows) and the routes that wire them up - GET
.../settlement, PUT .../settlement/{person_id}/paid, POST .../close
(design.md SS12)."""

import uuid
from decimal import Decimal

import pytest

from app.models.bill import Bill, BillStatus
from app.models.bill_item import BillItem
from app.models.bill_item_assignment import BillItemAssignment
from app.models.group import Group
from app.models.person import Person
from app.models.split import Split
from app.models.user import User
from app.services.settlement import ensure_settlement_rows, sync_bill_splits
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


def _open_bill_with_one_item(db, group, payer, assignee, price="10.00", tax="0"):
    bill = Bill(
        group_id=group.id,
        status=BillStatus.OPEN,
        tax_total=Decimal(tax),
        payer_person_id=payer.id if payer else None,
    )
    db.add(bill)
    db.flush()
    item = BillItem(bill_id=bill.id, parsed_name="Burger", price=Decimal(price))
    db.add(item)
    db.flush()
    db.add(
        BillItemAssignment(
            bill_item_id=item.id, person_id=assignee.id, is_predicted=False, share_fraction=1.0
        )
    )
    db.commit()
    return bill, item


# --- sync_bill_splits / ensure_settlement_rows ---


def test_sync_bill_splits_creates_one_row_per_person(db, group_with_two_people):
    group, alice, bob = group_with_two_people
    bill, _item = _open_bill_with_one_item(db, group, payer=alice, assignee=alice)

    rows = sync_bill_splits(db, bill)
    db.commit()

    assert {r.person_id for r in rows} == {alice.id, bob.id}
    alice_row = next(r for r in rows if r.person_id == alice.id)
    assert alice_row.total_owed == Decimal("10.00")
    assert alice_row.is_paid is False


def test_sync_bill_splits_preserves_is_paid_across_resync(db, group_with_two_people):
    group, alice, bob = group_with_two_people
    bill, item = _open_bill_with_one_item(db, group, payer=alice, assignee=alice)

    sync_bill_splits(db, bill)
    db.commit()
    bob_row = db.query(Split).filter(Split.bill_id == bill.id, Split.person_id == bob.id).one()
    bob_row.is_paid = True
    db.commit()

    # Reassigning the item changes the amounts, but shouldn't reset Bob's
    # is_paid - only app/services/settlement writes is_paid, and it must
    # carry it forward rather than clobber it on every resync.
    db.add(
        BillItemAssignment(
            bill_item_id=item.id, person_id=bob.id, is_predicted=False, share_fraction=1.0
        )
    )
    db.query(BillItemAssignment).filter(
        BillItemAssignment.bill_item_id == item.id, BillItemAssignment.person_id == alice.id
    ).delete()
    db.commit()
    db.refresh(bill)

    sync_bill_splits(db, bill)
    db.commit()
    bob_row = db.query(Split).filter(Split.bill_id == bill.id, Split.person_id == bob.id).one()
    assert bob_row.is_paid is True
    assert bob_row.total_owed == Decimal("10.00")  # now the sole assignee


def test_sync_bill_splits_drops_rows_for_people_no_longer_in_the_group(db, group_with_two_people):
    group, alice, bob = group_with_two_people
    bill, _item = _open_bill_with_one_item(db, group, payer=alice, assignee=alice)
    sync_bill_splits(db, bill)
    db.commit()
    assert db.query(Split).filter(Split.bill_id == bill.id).count() == 2

    db.delete(bob)
    db.commit()

    sync_bill_splits(db, bill)
    db.commit()
    remaining = db.query(Split).filter(Split.bill_id == bill.id).all()
    assert {r.person_id for r in remaining} == {alice.id}


def test_ensure_settlement_rows_rejects_bill_not_open_or_closed(db, group_with_two_people):
    group, alice, bob = group_with_two_people
    bill = Bill(group_id=group.id, status=BillStatus.NEEDS_REVIEW, tax_total=Decimal("0"))
    db.add(bill)
    db.commit()

    with pytest.raises(ValueError):
        ensure_settlement_rows(db, bill)


def test_ensure_settlement_rows_reads_frozen_rows_for_closed_bill_without_resyncing(
    db, group_with_two_people
):
    group, alice, bob = group_with_two_people
    bill, item = _open_bill_with_one_item(db, group, payer=alice, assignee=alice)
    sync_bill_splits(db, bill)
    db.commit()

    bill.status = BillStatus.CLOSED
    db.commit()

    # Change the item price after closing - a closed bill's Split rows
    # must stay exactly as they were, not pick this up.
    item.price = Decimal("999.00")
    db.commit()

    rows = ensure_settlement_rows(db, bill)
    alice_row = next(r for r in rows if r.person_id == alice.id)
    assert alice_row.total_owed == Decimal("10.00")


# --- API-level ---


def _setup_open_bill_via_api(client, headers, group_id):
    alice_id = client.post(
        f"/api/v1/groups/{group_id}/people", json={"display_name": "Alice"}, headers=headers
    ).json()["id"]
    bob_id = client.post(
        f"/api/v1/groups/{group_id}/people", json={"display_name": "Bob"}, headers=headers
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
    client.post(f"/api/v1/bills/{bill_id}/confirm", headers=headers)
    return bill_id, item_id, alice_id, bob_id


@pytest.fixture()
def open_bill_ctx(client, db_session_factory):
    db = db_session_factory()
    creator = User(id=uuid.uuid4(), email="creator@example.com")
    db.add(creator)
    db.commit()
    creator_id = creator.id
    db.close()

    headers = auth_headers(creator_id)
    group_id = client.post("/api/v1/groups", json={"name": "Roomies"}, headers=headers).json()["id"]
    bill_id, item_id, alice_id, bob_id = _setup_open_bill_via_api(client, headers, group_id)
    return {
        "headers": headers,
        "group_id": group_id,
        "bill_id": bill_id,
        "item_id": item_id,
        "alice_id": alice_id,
        "bob_id": bob_id,
    }


def test_get_settlement_creates_rows_once_bill_is_open(client, open_bill_ctx):
    ctx = open_bill_ctx
    resp = client.get(f"/api/v1/bills/{ctx['bill_id']}/settlement", headers=ctx["headers"])
    assert resp.status_code == 200
    body = {row["person_id"]: row for row in resp.json()}
    assert body[ctx["alice_id"]]["total_owed"] == "10.00"
    assert body[ctx["alice_id"]]["is_paid"] is False
    assert body[ctx["bob_id"]]["total_owed"] == "0.00"


def test_get_settlement_rejected_before_bill_is_open(client, db_session_factory):
    db = db_session_factory()
    creator = User(id=uuid.uuid4(), email="creator2@example.com")
    db.add(creator)
    db.commit()
    creator_id = creator.id
    db.close()

    headers = auth_headers(creator_id)
    group_id = client.post("/api/v1/groups", json={"name": "Roomies"}, headers=headers).json()["id"]
    bill_id = client.post(
        f"/api/v1/groups/{group_id}/bills", json={"merchant_name": "Diner"}, headers=headers
    ).json()["id"]

    resp = client.get(f"/api/v1/bills/{bill_id}/settlement", headers=headers)
    assert resp.status_code == 409


def test_set_split_paid_marks_and_unmarks(client, open_bill_ctx):
    ctx = open_bill_ctx
    resp = client.put(
        f"/api/v1/bills/{ctx['bill_id']}/settlement/{ctx['bob_id']}/paid",
        json={"is_paid": True},
        headers=ctx["headers"],
    )
    assert resp.status_code == 200
    assert resp.json()["is_paid"] is True
    assert resp.json()["paid_at"] is not None

    resp = client.put(
        f"/api/v1/bills/{ctx['bill_id']}/settlement/{ctx['bob_id']}/paid",
        json={"is_paid": False},
        headers=ctx["headers"],
    )
    assert resp.json()["is_paid"] is False
    assert resp.json()["paid_at"] is None


def test_set_split_paid_rejects_payer_marking_their_own_split(client, open_bill_ctx):
    ctx = open_bill_ctx
    client.put(
        f"/api/v1/bills/{ctx['bill_id']}/payer",
        json={"person_id": ctx["alice_id"]},
        headers=ctx["headers"],
    )
    resp = client.put(
        f"/api/v1/bills/{ctx['bill_id']}/settlement/{ctx['alice_id']}/paid",
        json={"is_paid": True},
        headers=ctx["headers"],
    )
    assert resp.status_code == 422


def test_close_bill_requires_a_payer(client, open_bill_ctx):
    ctx = open_bill_ctx
    resp = client.post(f"/api/v1/bills/{ctx['bill_id']}/close", headers=ctx["headers"])
    assert resp.status_code == 422


def test_close_bill_requires_every_non_payer_split_paid(client, open_bill_ctx):
    ctx = open_bill_ctx
    client.put(
        f"/api/v1/bills/{ctx['bill_id']}/payer",
        json={"person_id": ctx["alice_id"]},
        headers=ctx["headers"],
    )

    resp = client.post(f"/api/v1/bills/{ctx['bill_id']}/close", headers=ctx["headers"])
    assert resp.status_code == 409  # Bob hasn't been marked paid yet

    client.put(
        f"/api/v1/bills/{ctx['bill_id']}/settlement/{ctx['bob_id']}/paid",
        json={"is_paid": True},
        headers=ctx["headers"],
    )
    resp = client.post(f"/api/v1/bills/{ctx['bill_id']}/close", headers=ctx["headers"])
    assert resp.status_code == 200
    assert resp.json()["status"] == "closed"
    assert resp.json()["closed_at"] is not None


def test_closed_bill_settlement_is_immutable(client, open_bill_ctx):
    ctx = open_bill_ctx
    client.put(
        f"/api/v1/bills/{ctx['bill_id']}/payer",
        json={"person_id": ctx["alice_id"]},
        headers=ctx["headers"],
    )
    client.put(
        f"/api/v1/bills/{ctx['bill_id']}/settlement/{ctx['bob_id']}/paid",
        json={"is_paid": True},
        headers=ctx["headers"],
    )
    client.post(f"/api/v1/bills/{ctx['bill_id']}/close", headers=ctx["headers"])

    resp = client.put(
        f"/api/v1/bills/{ctx['bill_id']}/settlement/{ctx['bob_id']}/paid",
        json={"is_paid": False},
        headers=ctx["headers"],
    )
    assert resp.status_code == 409

    resp = client.post(f"/api/v1/bills/{ctx['bill_id']}/close", headers=ctx["headers"])
    assert resp.status_code == 409  # already closed


def test_close_bill_rejected_when_not_open(client, db_session_factory):
    db = db_session_factory()
    creator = User(id=uuid.uuid4(), email="creator3@example.com")
    db.add(creator)
    db.commit()
    creator_id = creator.id
    db.close()

    headers = auth_headers(creator_id)
    group_id = client.post("/api/v1/groups", json={"name": "Roomies"}, headers=headers).json()["id"]
    bill_id = client.post(
        f"/api/v1/groups/{group_id}/bills", json={"merchant_name": "Diner"}, headers=headers
    ).json()[
        "id"
    ]  # still needs_manual_entry

    resp = client.post(f"/api/v1/bills/{bill_id}/close", headers=headers)
    assert resp.status_code == 409
