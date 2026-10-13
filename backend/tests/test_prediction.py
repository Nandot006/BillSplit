import uuid
from decimal import Decimal

import pytest

from app.models.bill import Bill, BillStatus
from app.models.bill_item import BillItem
from app.models.bill_item_tags import BillItemDietaryFlag, BillItemFlavorTag
from app.models.group import Group
from app.models.person import Person
from app.models.person_taxonomy_score import PersonTaxonomyScore
from app.models.prediction_feedback import PredictionFeedback
from app.models.taxonomy import BaseType, DietaryFlag, FlavorTag, TaxonomySource, TaxonomyValue
from app.models.user import User
from app.services.prediction.pipeline import (
    BASE_LEARNING_RATE,
    apply_learned_correction,
    generate_predictions_for_bill,
    record_correction,
)
from tests.auth_helpers import auth_headers

# --- direct-DB unit tests for the pipeline functions ---


@pytest.fixture()
def db(db_session_factory):
    session = db_session_factory()
    yield session
    session.close()


@pytest.fixture()
def group_with_people(db):
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


def _make_item(db, bill, base_type=BaseType.ENTREE):
    item = BillItem(
        bill_id=bill.id, parsed_name="Pizza", price=Decimal("10.00"), base_type=base_type
    )
    db.add(item)
    db.flush()
    return item


def test_generate_predictions_skips_items_that_already_have_an_assignment(db, group_with_people):
    group, alice, bob = group_with_people
    bill = Bill(group_id=group.id, status=BillStatus.NEEDS_REVIEW)
    db.add(bill)
    db.flush()
    item = _make_item(db, bill)
    record_correction(db, item, bob.id)  # manually assign before predictions ever run
    db.commit()

    generate_predictions_for_bill(db, bill)
    db.refresh(item)
    assert len(item.assignments) == 1
    assert item.assignments[0].person_id == bob.id
    assert item.assignments[0].is_predicted is False  # untouched by the scorer


def test_generate_predictions_leaves_item_unassigned_when_hard_restriction_excludes_everyone(
    db, group_with_people
):
    group, alice, bob = group_with_people
    db.add(
        PersonTaxonomyScore(
            person_id=alice.id,
            taxonomy_value=TaxonomyValue.VEGAN,
            score=1.0,
            is_hard_restriction=True,
            source=TaxonomySource.QUESTIONNAIRE,
        )
    )
    db.add(
        PersonTaxonomyScore(
            person_id=bob.id,
            taxonomy_value=TaxonomyValue.VEGAN,
            score=1.0,
            is_hard_restriction=True,
            source=TaxonomySource.QUESTIONNAIRE,
        )
    )
    db.commit()

    bill = Bill(group_id=group.id, status=BillStatus.NEEDS_REVIEW)
    db.add(bill)
    db.flush()
    item = _make_item(db, bill)
    db.add(BillItemDietaryFlag(bill_item_id=item.id, dietary_flag=DietaryFlag.VEGETARIAN))
    db.commit()  # tagged vegetarian, not vegan - excludes both hard-vegan people

    generate_predictions_for_bill(db, bill)
    db.refresh(item)
    assert item.assignments == []


def test_apply_learned_correction_shrinking_rate_and_clamping(db, group_with_people):
    group, alice, bob = group_with_people
    bill = Bill(group_id=group.id, status=BillStatus.NEEDS_REVIEW)
    db.add(bill)
    db.flush()
    item = _make_item(db, bill)
    db.add(BillItemFlavorTag(bill_item_id=item.id, flavor_tag=FlavorTag.SPICY))
    db.commit()

    # First correction: full base rate (correction_count starts at 0).
    apply_learned_correction(db, item, original_person_id=bob.id, corrected_person_id=alice.id)
    alice_entree = (
        db.query(PersonTaxonomyScore)
        .filter(
            PersonTaxonomyScore.person_id == alice.id,
            PersonTaxonomyScore.taxonomy_value == TaxonomyValue.ENTREE,
        )
        .one()
    )
    assert alice_entree.score == pytest.approx(BASE_LEARNING_RATE)
    assert alice_entree.correction_count == 1
    assert alice_entree.source == TaxonomySource.LEARNED_CORRECTION

    bob_entree = (
        db.query(PersonTaxonomyScore)
        .filter(
            PersonTaxonomyScore.person_id == bob.id,
            PersonTaxonomyScore.taxonomy_value == TaxonomyValue.ENTREE,
        )
        .one()
    )
    assert bob_entree.score == pytest.approx(-BASE_LEARNING_RATE)

    # Second correction on the same dimension: rate has decayed (denominator 2).
    apply_learned_correction(db, item, original_person_id=bob.id, corrected_person_id=alice.id)
    db.refresh(alice_entree)
    assert alice_entree.score == pytest.approx(BASE_LEARNING_RATE + BASE_LEARNING_RATE / 2)
    assert alice_entree.correction_count == 2


def test_apply_learned_correction_clamps_score_to_valid_range(db, group_with_people):
    group, alice, bob = group_with_people
    bill = Bill(group_id=group.id, status=BillStatus.NEEDS_REVIEW)
    db.add(bill)
    db.flush()
    item = _make_item(db, bill)
    db.commit()

    for _ in range(20):
        apply_learned_correction(db, item, original_person_id=None, corrected_person_id=alice.id)

    score = (
        db.query(PersonTaxonomyScore)
        .filter(
            PersonTaxonomyScore.person_id == alice.id,
            PersonTaxonomyScore.taxonomy_value == TaxonomyValue.ENTREE,
        )
        .one()
    )
    assert score.score <= 1.0


def test_record_correction_is_noop_when_person_already_the_sole_assignee(db, group_with_people):
    group, alice, bob = group_with_people
    bill = Bill(group_id=group.id, status=BillStatus.NEEDS_REVIEW)
    db.add(bill)
    db.flush()
    item = _make_item(db, bill)
    db.commit()
    record_correction(db, item, alice.id)
    db.commit()
    feedback_count_before = db.query(PredictionFeedback).count()

    record_correction(db, item, alice.id)  # re-confirming the same person
    db.commit()

    assert db.query(PredictionFeedback).count() == feedback_count_before


def test_record_correction_writes_feedback_with_no_original_when_nothing_was_predicted(
    db, group_with_people
):
    group, alice, bob = group_with_people
    bill = Bill(group_id=group.id, status=BillStatus.NEEDS_REVIEW)
    db.add(bill)
    db.flush()
    item = _make_item(db, bill)
    db.commit()

    record_correction(db, item, alice.id)
    db.commit()

    feedback = db.query(PredictionFeedback).filter(PredictionFeedback.bill_item_id == item.id).one()
    assert feedback.original_predicted_person_id is None
    assert feedback.corrected_person_id == alice.id


# --- API-level integration tests: the review/confirm flow end to end ---


@pytest.fixture()
def group_with_people_via_api(client, db_session_factory):
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


def _finalize_bill_with_one_item(client, ctx):
    headers = auth_headers(ctx["creator_id"])
    bill_id = client.post(
        f"/api/v1/groups/{ctx['group_id']}/bills", json={"merchant_name": "Diner"}, headers=headers
    ).json()["id"]
    client.post(
        f"/api/v1/bills/{bill_id}/items",
        json={"parsed_name": "Burger", "price": "10.00", "base_type": "entree"},
        headers=headers,
    )
    resp = client.post(f"/api/v1/bills/{bill_id}/finalize-manual-entry", headers=headers)
    assert resp.status_code == 200
    return bill_id


def test_assign_endpoint_corrects_prediction_and_updates_learning(
    client, group_with_people_via_api
):
    ctx = group_with_people_via_api
    headers = auth_headers(ctx["creator_id"])
    bill_id = _finalize_bill_with_one_item(client, ctx)

    bill = client.get(f"/api/v1/bills/{bill_id}", headers=headers).json()
    item = bill["items"][0]
    # With no taxonomy scores seeded, both People tie at score 0.0 - the
    # scorer still picks an arbitrary winner rather than leaving the item
    # unassigned (design.md SS6: only a hard restriction that excludes
    # every candidate does that - see test_confirm_requires_every_item_...
    # below for that case). Exactly one predicted assignment exists here.
    assert len(item["assignments"]) == 1
    original_winner_id = item["assignments"][0]["person_id"]
    other_person_id = ctx["bob_id"] if original_winner_id == ctx["alice_id"] else ctx["alice_id"]

    resp = client.put(
        f"/api/v1/bills/{bill_id}/items/{item['id']}/assign",
        json={"person_id": other_person_id},
        headers=headers,
    )
    assert resp.status_code == 200
    assignments = resp.json()["assignments"]
    assert len(assignments) == 1
    assert assignments[0]["person_id"] == other_person_id
    assert assignments[0]["is_predicted"] is False


def test_assign_endpoint_rejects_person_from_another_group(client, group_with_people_via_api):
    ctx = group_with_people_via_api
    headers = auth_headers(ctx["creator_id"])
    bill_id = _finalize_bill_with_one_item(client, ctx)
    bill = client.get(f"/api/v1/bills/{bill_id}", headers=headers).json()
    item_id = bill["items"][0]["id"]

    resp = client.put(
        f"/api/v1/bills/{bill_id}/items/{item_id}/assign",
        json={"person_id": str(uuid.uuid4())},
        headers=headers,
    )
    assert resp.status_code == 422


def test_confirm_requires_every_item_assigned_then_moves_bill_to_open(
    client, group_with_people_via_api, db_session_factory
):
    ctx = group_with_people_via_api
    headers = auth_headers(ctx["creator_id"])

    # Give both People a hard vegan restriction, then tag the only item
    # vegetarian (not vegan) - design.md SS6's edge case where a hard
    # restriction excludes every candidate, so the scorer leaves the item
    # with no assignment at all for confirm to catch.
    db = db_session_factory()
    for person_id in (ctx["alice_id"], ctx["bob_id"]):
        db.add(
            PersonTaxonomyScore(
                person_id=uuid.UUID(person_id),
                taxonomy_value=TaxonomyValue.VEGAN,
                score=1.0,
                is_hard_restriction=True,
                source=TaxonomySource.QUESTIONNAIRE,
            )
        )
    db.commit()
    db.close()

    bill_id = client.post(
        f"/api/v1/groups/{ctx['group_id']}/bills", json={"merchant_name": "Diner"}, headers=headers
    ).json()["id"]
    client.post(
        f"/api/v1/bills/{bill_id}/items",
        json={"parsed_name": "Veggie Wrap", "price": "10.00", "dietary_flags": ["vegetarian"]},
        headers=headers,
    )
    client.post(f"/api/v1/bills/{bill_id}/finalize-manual-entry", headers=headers)

    bill = client.get(f"/api/v1/bills/{bill_id}", headers=headers).json()
    item_id = bill["items"][0]["id"]
    assert bill["items"][0]["assignments"] == []  # hard restriction excluded everyone

    resp = client.post(f"/api/v1/bills/{bill_id}/confirm", headers=headers)
    assert resp.status_code == 422  # nothing assigned yet

    client.put(
        f"/api/v1/bills/{bill_id}/items/{item_id}/assign",
        json={"person_id": ctx["alice_id"]},
        headers=headers,
    )
    resp = client.post(f"/api/v1/bills/{bill_id}/confirm", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "open"


def test_confirm_rejects_bill_not_in_needs_review(client, group_with_people_via_api):
    ctx = group_with_people_via_api
    headers = auth_headers(ctx["creator_id"])
    bill_id = client.post(
        f"/api/v1/groups/{ctx['group_id']}/bills", json={"merchant_name": "Diner"}, headers=headers
    ).json()[
        "id"
    ]  # still needs_manual_entry, no items

    resp = client.post(f"/api/v1/bills/{bill_id}/confirm", headers=headers)
    assert resp.status_code == 409


def test_assign_rejected_once_bill_is_closed(client, group_with_people_via_api, db_session_factory):
    ctx = group_with_people_via_api
    headers = auth_headers(ctx["creator_id"])
    bill_id = _finalize_bill_with_one_item(client, ctx)
    bill = client.get(f"/api/v1/bills/{bill_id}", headers=headers).json()
    item_id = bill["items"][0]["id"]
    client.put(
        f"/api/v1/bills/{bill_id}/items/{item_id}/assign",
        json={"person_id": ctx["alice_id"]},
        headers=headers,
    )
    client.post(f"/api/v1/bills/{bill_id}/confirm", headers=headers)

    db = db_session_factory()
    bill_row = db.get(Bill, uuid.UUID(bill_id))
    bill_row.status = BillStatus.CLOSED
    db.commit()
    db.close()

    resp = client.put(
        f"/api/v1/bills/{bill_id}/items/{item_id}/assign",
        json={"person_id": ctx["bob_id"]},
        headers=headers,
    )
    assert resp.status_code == 409
