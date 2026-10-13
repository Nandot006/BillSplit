"""Backend Block 10: redistribute_bill_after_person_removal (item
re-scoring / share re-normalization) and the group-removal endpoint that
calls it, including the closed-bill-immutability guard."""

import uuid
from decimal import Decimal

import pytest

from app.models.bill import Bill, BillStatus
from app.models.bill_item import BillItem
from app.models.bill_item_assignment import BillItemAssignment
from app.models.bill_item_tags import BillItemDietaryFlag
from app.models.group import Group
from app.models.person import Person
from app.models.person_taxonomy_score import PersonTaxonomyScore
from app.models.taxonomy import DietaryFlag, TaxonomySource, TaxonomyValue
from app.models.user import User
from app.services.prediction.pipeline import redistribute_bill_after_person_removal
from tests.auth_helpers import auth_headers


@pytest.fixture()
def db(db_session_factory):
    session = db_session_factory()
    yield session
    session.close()


@pytest.fixture()
def group_with_three_people(db):
    creator = User(id=uuid.uuid4(), email="creator@example.com")
    db.add(creator)
    db.flush()
    group = Group(name="Dinner", creator_user_id=creator.id)
    db.add(group)
    db.flush()
    alice = Person(group_id=group.id, display_name="Alice")
    bob = Person(group_id=group.id, display_name="Bob")
    cara = Person(group_id=group.id, display_name="Cara")
    db.add_all([alice, bob, cara])
    db.commit()
    return group, alice, bob, cara


def _make_item(db, bill, price="10.00"):
    item = BillItem(bill_id=bill.id, parsed_name="Item", price=Decimal(price))
    db.add(item)
    db.flush()
    return item


def test_shared_item_shares_are_renormalized_when_one_assignee_is_removed(
    db, group_with_three_people
):
    group, alice, bob, cara = group_with_three_people
    bill = Bill(group_id=group.id, status=BillStatus.OPEN)
    db.add(bill)
    db.flush()
    item = _make_item(db, bill)
    for person in (alice, bob, cara):
        db.add(
            BillItemAssignment(
                bill_item_id=item.id, person_id=person.id, is_predicted=False, share_fraction=1 / 3
            )
        )
    db.commit()

    needs_review = redistribute_bill_after_person_removal(db, bill, alice.id)
    db.commit()

    assert needs_review is False
    db.refresh(item)
    remaining = {a.person_id: a.share_fraction for a in item.assignments}
    assert set(remaining) == {bob.id, cara.id}
    assert remaining[bob.id] == pytest.approx(0.5)
    assert remaining[cara.id] == pytest.approx(0.5)


def test_sole_assignee_item_is_rescored_against_remaining_people_only(db, group_with_three_people):
    group, alice, bob, cara = group_with_three_people
    # Bob strongly prefers entrees; Cara has no signal at all - Bob should
    # win the re-score once Alice (the item's current sole assignee) is
    # removed and it's re-run against {Bob, Cara}.
    db.add(
        PersonTaxonomyScore(
            person_id=bob.id,
            taxonomy_value=TaxonomyValue.ENTREE,
            score=1.0,
            source=TaxonomySource.QUESTIONNAIRE,
        )
    )
    db.commit()

    bill = Bill(group_id=group.id, status=BillStatus.OPEN)
    db.add(bill)
    db.flush()
    item = BillItem(
        bill_id=bill.id,
        parsed_name="Burger",
        price=Decimal("10.00"),
        base_type=__import__("app.models.taxonomy", fromlist=["BaseType"]).BaseType.ENTREE,
    )
    db.add(item)
    db.flush()
    db.add(
        BillItemAssignment(
            bill_item_id=item.id, person_id=alice.id, is_predicted=False, share_fraction=1.0
        )
    )
    db.commit()

    needs_review = redistribute_bill_after_person_removal(db, bill, alice.id)
    db.commit()

    assert needs_review is False
    db.refresh(item)
    assert len(item.assignments) == 1
    assert item.assignments[0].person_id == bob.id
    assert item.assignments[0].is_predicted is True


def test_item_left_unassigned_when_hard_restriction_excludes_all_remaining_people(
    db, group_with_three_people
):
    group, alice, bob, cara = group_with_three_people
    for person in (bob, cara):
        db.add(
            PersonTaxonomyScore(
                person_id=person.id,
                taxonomy_value=TaxonomyValue.VEGAN,
                score=1.0,
                is_hard_restriction=True,
                source=TaxonomySource.QUESTIONNAIRE,
            )
        )
    db.commit()

    bill = Bill(group_id=group.id, status=BillStatus.OPEN)
    db.add(bill)
    db.flush()
    item = _make_item(db, bill)
    db.add(BillItemDietaryFlag(bill_item_id=item.id, dietary_flag=DietaryFlag.VEGETARIAN))
    db.add(
        BillItemAssignment(
            bill_item_id=item.id, person_id=alice.id, is_predicted=False, share_fraction=1.0
        )
    )
    db.commit()

    needs_review = redistribute_bill_after_person_removal(db, bill, alice.id)
    db.commit()

    assert needs_review is True
    db.refresh(item)
    assert item.assignments == []


def test_returns_false_when_person_had_no_assignments_on_this_bill(db, group_with_three_people):
    group, alice, bob, cara = group_with_three_people
    bill = Bill(group_id=group.id, status=BillStatus.OPEN)
    db.add(bill)
    db.flush()
    item = _make_item(db, bill)
    db.add(
        BillItemAssignment(
            bill_item_id=item.id, person_id=bob.id, is_predicted=False, share_fraction=1.0
        )
    )
    db.commit()

    assert redistribute_bill_after_person_removal(db, bill, alice.id) is False


# --- API-level: the remove-person endpoint end to end ---


@pytest.fixture()
def group_ctx(client, db_session_factory):
    db = db_session_factory()
    creator = User(id=uuid.uuid4(), email="creator2@example.com")
    db.add(creator)
    db.commit()
    creator_id = creator.id
    db.close()

    headers = auth_headers(creator_id)
    group_id = client.post("/api/v1/groups", json={"name": "Roomies"}, headers=headers).json()["id"]
    alice_id = client.post(
        f"/api/v1/groups/{group_id}/people", json={"display_name": "Alice"}, headers=headers
    ).json()["id"]
    bob_id = client.post(
        f"/api/v1/groups/{group_id}/people", json={"display_name": "Bob"}, headers=headers
    ).json()["id"]
    return {"creator_id": creator_id, "group_id": group_id, "alice_id": alice_id, "bob_id": bob_id}


def test_remove_person_redistributes_open_bill_items(client, group_ctx, db_session_factory):
    headers = auth_headers(group_ctx["creator_id"])
    bill_id = client.post(
        f"/api/v1/groups/{group_ctx['group_id']}/bills",
        json={"merchant_name": "Diner"},
        headers=headers,
    ).json()["id"]
    item_id = client.post(
        f"/api/v1/bills/{bill_id}/items",
        json={"parsed_name": "Burger", "price": "10.00"},
        headers=headers,
    ).json()["id"]
    client.post(f"/api/v1/bills/{bill_id}/finalize-manual-entry", headers=headers)
    client.put(
        f"/api/v1/bills/{bill_id}/items/{item_id}/assign",
        json={"person_id": group_ctx["alice_id"]},
        headers=headers,
    )
    client.post(f"/api/v1/bills/{bill_id}/confirm", headers=headers)

    delete_resp = client.delete(
        f"/api/v1/groups/{group_ctx['group_id']}/people/{group_ctx['alice_id']}", headers=headers
    )
    assert delete_resp.status_code == 204

    bill = client.get(f"/api/v1/bills/{bill_id}", headers=headers).json()
    # With no taxonomy scores seeded, Bob is the only remaining candidate -
    # the item is re-scored onto him rather than left with the now-deleted
    # Alice or with no one at all.
    assert len(bill["items"][0]["assignments"]) == 1
    assert bill["items"][0]["assignments"][0]["person_id"] == group_ctx["bob_id"]
    assert bill["status"] == "open"


def test_cannot_remove_person_with_history_on_a_closed_bill(client, group_ctx, db_session_factory):
    headers = auth_headers(group_ctx["creator_id"])
    bill_id = client.post(
        f"/api/v1/groups/{group_ctx['group_id']}/bills",
        json={"merchant_name": "Diner"},
        headers=headers,
    ).json()["id"]
    item_id = client.post(
        f"/api/v1/bills/{bill_id}/items",
        json={"parsed_name": "Burger", "price": "10.00"},
        headers=headers,
    ).json()["id"]
    client.post(f"/api/v1/bills/{bill_id}/finalize-manual-entry", headers=headers)
    client.put(
        f"/api/v1/bills/{bill_id}/items/{item_id}/assign",
        json={"person_id": group_ctx["alice_id"]},
        headers=headers,
    )
    client.post(f"/api/v1/bills/{bill_id}/confirm", headers=headers)

    db = db_session_factory()
    bill_row = db.get(Bill, uuid.UUID(bill_id))
    bill_row.status = BillStatus.CLOSED
    db.commit()
    db.close()

    resp = client.delete(
        f"/api/v1/groups/{group_ctx['group_id']}/people/{group_ctx['alice_id']}", headers=headers
    )
    assert resp.status_code == 409

    # Untouched by the failed removal - still there, still assigned.
    get_resp = client.get(f"/api/v1/people/{group_ctx['alice_id']}", headers=headers)
    assert get_resp.status_code == 200
