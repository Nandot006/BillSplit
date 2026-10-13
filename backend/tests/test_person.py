import uuid

import pytest

from app.models.group import Group
from app.models.person import Person
from app.models.user import User
from tests.auth_helpers import auth_headers


@pytest.fixture()
def seeded(db_session_factory):
    db = db_session_factory()
    creator = User(id=uuid.uuid4(), email="creator@example.com", display_name="Creator")
    outsider = User(id=uuid.uuid4(), email="outsider@example.com", display_name="Outsider")
    db.add_all([creator, outsider])
    db.flush()

    group = Group(id=uuid.uuid4(), name="Dinner Crew", creator_user_id=creator.id)
    db.add(group)
    db.flush()

    person = Person(
        id=uuid.uuid4(), group_id=group.id, display_name="Alex", free_text_preferences="vegetarian"
    )
    db.add(person)
    db.commit()

    ids = {
        "creator_id": creator.id,
        "outsider_id": outsider.id,
        "group_id": group.id,
        "person_id": person.id,
    }
    db.close()
    return ids


def test_creator_can_view_person(client, seeded):
    resp = client.get(
        f"/api/v1/people/{seeded['person_id']}", headers=auth_headers(seeded["creator_id"])
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["display_name"] == "Alex"
    assert body["free_text_preferences"] == "vegetarian"


def test_outsider_gets_404_not_403(client, seeded):
    """CLAUDE.md SS9: enforce group-sharing at the API layer. A 404 (not a
    403) is deliberate - it shouldn't be possible to tell a person/group
    exists at all from outside the group."""
    resp = client.get(
        f"/api/v1/people/{seeded['person_id']}", headers=auth_headers(seeded["outsider_id"])
    )
    assert resp.status_code == 404


def test_creator_can_update_person(client, seeded):
    resp = client.patch(
        f"/api/v1/people/{seeded['person_id']}",
        json={"free_text_preferences": "vegan now"},
        headers=auth_headers(seeded["creator_id"]),
    )
    assert resp.status_code == 200
    assert resp.json()["free_text_preferences"] == "vegan now"


def test_outsider_cannot_update_person(client, seeded):
    resp = client.patch(
        f"/api/v1/people/{seeded['person_id']}",
        json={"free_text_preferences": "hacked"},
        headers=auth_headers(seeded["outsider_id"]),
    )
    assert resp.status_code == 404


def test_unauthenticated_request_is_rejected(client, seeded):
    resp = client.get(f"/api/v1/people/{seeded['person_id']}")
    assert resp.status_code == 401


def test_nonexistent_person_is_404(client, seeded):
    resp = client.get(f"/api/v1/people/{uuid.uuid4()}", headers=auth_headers(seeded["creator_id"]))
    assert resp.status_code == 404
