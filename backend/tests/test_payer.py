"""Backend Block 11: app/services/payer (suggest_payer, record_payer_change)
and the routes that wire them up - PUT /bills/{bill_id}/payer and
GET /groups/{group_id}/payer-suggestion (design.md SS11)."""

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.models.bill import Bill, BillStatus
from app.models.group import Group
from app.models.payer_history import PayerHistory
from app.models.person import Person
from app.models.user import User
from app.services.payer import record_payer_change, suggest_payer
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


# --- suggest_payer ---


def test_suggest_payer_with_no_history_ties_alphabetically(db, group_with_two_people):
    group, alice, bob = group_with_two_people
    # Neither has ever paid - both are NULL last_paid_at, so the
    # alphabetical tie-break decides: Alice.
    suggestion = suggest_payer(db, group.id)
    assert suggestion.id == alice.id


def test_suggest_payer_prefers_least_recently_paid(db, group_with_two_people):
    group, alice, bob = group_with_two_people
    now = datetime.now(timezone.utc)
    db.add_all(
        [
            PayerHistory(group_id=group.id, person_id=alice.id, payment_count=3, last_paid_at=now),
            PayerHistory(
                group_id=group.id,
                person_id=bob.id,
                payment_count=1,
                last_paid_at=now - timedelta(days=5),
            ),
        ]
    )
    db.commit()

    # Bob paid longer ago than Alice, so he's suggested despite having
    # paid fewer times overall - recency drives this, not the count.
    suggestion = suggest_payer(db, group.id)
    assert suggestion.id == bob.id


def test_suggest_payer_never_paid_beats_anyone_with_history(db, group_with_two_people):
    group, alice, bob = group_with_two_people
    db.add(
        PayerHistory(
            group_id=group.id,
            person_id=bob.id,
            payment_count=1,
            last_paid_at=datetime(2000, 1, 1, tzinfo=timezone.utc),
        )
    )
    db.commit()

    # Alice has no PayerHistory row at all (never paid) - that beats even
    # Bob's very old payment, per design.md SS11's NULL-sorts-first rule.
    suggestion = suggest_payer(db, group.id)
    assert suggestion.id == alice.id


def test_suggest_payer_with_no_people_returns_none(db):
    creator = User(id=uuid.uuid4(), email="lonely@example.com")
    db.add(creator)
    db.flush()
    empty_group = Group(name="Empty", creator_user_id=creator.id)
    db.add(empty_group)
    db.commit()

    assert suggest_payer(db, empty_group.id) is None


# --- record_payer_change ---


def test_record_payer_change_increments_new_and_decrements_old(db, group_with_two_people):
    group, alice, bob = group_with_two_people
    record_payer_change(db, group.id, None, alice.id)
    db.commit()

    alice_row = db.get(PayerHistory, (group.id, alice.id))
    assert alice_row.payment_count == 1
    assert alice_row.last_paid_at is not None

    record_payer_change(db, group.id, alice.id, bob.id)
    db.commit()

    alice_row = db.get(PayerHistory, (group.id, alice.id))
    bob_row = db.get(PayerHistory, (group.id, bob.id))
    assert alice_row.payment_count == 0
    assert bob_row.payment_count == 1


def test_record_payer_change_is_noop_when_unchanged(db, group_with_two_people):
    group, alice, bob = group_with_two_people
    record_payer_change(db, group.id, None, alice.id)
    db.commit()
    first_last_paid_at = db.get(PayerHistory, (group.id, alice.id)).last_paid_at

    # Re-recording the same payer must not double-count.
    record_payer_change(db, group.id, alice.id, alice.id)
    db.commit()

    row = db.get(PayerHistory, (group.id, alice.id))
    assert row.payment_count == 1
    assert row.last_paid_at == first_last_paid_at


def test_record_payer_change_decrement_does_not_go_negative(db, group_with_two_people):
    group, alice, bob = group_with_two_people
    # Alice has never actually been recorded as payer (no PayerHistory row
    # at all), but the bill claims she was the old payer (defensive edge
    # case) - there's nothing to decrement, so no row should be created
    # for her, and certainly not a negative count.
    record_payer_change(db, group.id, alice.id, bob.id)
    db.commit()

    alice_row = db.get(PayerHistory, (group.id, alice.id))
    assert alice_row is None or alice_row.payment_count == 0


# --- API-level ---


def _setup_group_and_bill(client, headers):
    group_id = client.post("/api/v1/groups", json={"name": "Roomies"}, headers=headers).json()["id"]
    alice_id = client.post(
        f"/api/v1/groups/{group_id}/people", json={"display_name": "Alice"}, headers=headers
    ).json()["id"]
    bob_id = client.post(
        f"/api/v1/groups/{group_id}/people", json={"display_name": "Bob"}, headers=headers
    ).json()["id"]
    bill_id = client.post(
        f"/api/v1/groups/{group_id}/bills", json={"merchant_name": "Diner"}, headers=headers
    ).json()["id"]
    return group_id, alice_id, bob_id, bill_id


def test_set_bill_payer_and_read_back_on_bill(client, db_session_factory):
    db = db_session_factory()
    creator = User(id=uuid.uuid4(), email="creator2@example.com")
    db.add(creator)
    db.commit()
    creator_id = creator.id
    db.close()

    headers = auth_headers(creator_id)
    group_id, alice_id, _bob_id, bill_id = _setup_group_and_bill(client, headers)

    resp = client.put(
        f"/api/v1/bills/{bill_id}/payer", json={"person_id": alice_id}, headers=headers
    )
    assert resp.status_code == 200
    assert resp.json()["payer_person_id"] == alice_id

    bill_resp = client.get(f"/api/v1/bills/{bill_id}", headers=headers)
    assert bill_resp.json()["payer_person_id"] == alice_id


def test_set_bill_payer_rejects_person_from_another_group(client, db_session_factory):
    db = db_session_factory()
    creator = User(id=uuid.uuid4(), email="creator3@example.com")
    db.add(creator)
    db.commit()
    creator_id = creator.id
    db.close()

    headers = auth_headers(creator_id)
    _group_id, _alice_id, _bob_id, bill_id = _setup_group_and_bill(client, headers)

    other_group_id = client.post("/api/v1/groups", json={"name": "Other"}, headers=headers).json()[
        "id"
    ]
    outsider_id = client.post(
        f"/api/v1/groups/{other_group_id}/people",
        json={"display_name": "Outsider"},
        headers=headers,
    ).json()["id"]

    resp = client.put(
        f"/api/v1/bills/{bill_id}/payer", json={"person_id": outsider_id}, headers=headers
    )
    assert resp.status_code == 422


def test_get_payer_suggestion_updates_after_setting_payer(client, db_session_factory):
    db = db_session_factory()
    creator = User(id=uuid.uuid4(), email="creator4@example.com")
    db.add(creator)
    db.commit()
    creator_id = creator.id
    db.close()

    headers = auth_headers(creator_id)
    group_id, alice_id, bob_id, bill_id = _setup_group_and_bill(client, headers)

    # Nobody has paid yet - alphabetical tie-break picks Alice.
    resp = client.get(f"/api/v1/groups/{group_id}/payer-suggestion", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["person_id"] == alice_id
    assert resp.json()["payment_count"] == 0

    client.put(f"/api/v1/bills/{bill_id}/payer", json={"person_id": alice_id}, headers=headers)

    # Now Alice has paid most recently (and only) - Bob (never paid) is
    # suggested next.
    resp = client.get(f"/api/v1/groups/{group_id}/payer-suggestion", headers=headers)
    assert resp.json()["person_id"] == bob_id


def test_set_bill_payer_blocked_once_bill_is_closed(client, db_session_factory):
    db = db_session_factory()
    creator = User(id=uuid.uuid4(), email="creator5@example.com")
    db.add(creator)
    db.commit()
    creator_id = creator.id
    db.close()

    headers = auth_headers(creator_id)
    _group_id, alice_id, _bob_id, bill_id = _setup_group_and_bill(client, headers)
    client.put(f"/api/v1/bills/{bill_id}/payer", json={"person_id": alice_id}, headers=headers)

    # Force the bill closed directly via the DB (Block 12 hasn't wired up
    # the real close endpoint yet), then confirm it's now immutable here.
    db = db_session_factory()
    bill = db.get(Bill, uuid.UUID(bill_id))
    bill.status = BillStatus.CLOSED
    db.commit()
    db.close()

    resp = client.put(
        f"/api/v1/bills/{bill_id}/payer", json={"person_id": alice_id}, headers=headers
    )
    assert resp.status_code == 409
