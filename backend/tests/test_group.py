import uuid

import pytest

from app.models.person import Person
from app.models.user import User
from tests.auth_helpers import auth_headers


@pytest.fixture()
def two_users(db_session_factory):
    db = db_session_factory()
    creator = User(id=uuid.uuid4(), email="creator@example.com")
    outsider = User(id=uuid.uuid4(), email="outsider@example.com")
    db.add_all([creator, outsider])
    db.commit()
    ids = {"creator_id": creator.id, "outsider_id": outsider.id}
    db.close()
    return ids


def test_create_and_get_group(client, two_users):
    resp = client.post(
        "/api/v1/groups",
        json={"name": "Dinner Crew"},
        headers=auth_headers(two_users["creator_id"]),
    )
    assert resp.status_code == 201
    group_id = resp.json()["id"]
    assert resp.json()["creator_user_id"] == str(two_users["creator_id"])

    get_resp = client.get(
        f"/api/v1/groups/{group_id}", headers=auth_headers(two_users["creator_id"])
    )
    assert get_resp.status_code == 200
    assert get_resp.json()["people"] == []


def test_outsider_cannot_see_group(client, two_users):
    create_resp = client.post(
        "/api/v1/groups",
        json={"name": "Dinner Crew"},
        headers=auth_headers(two_users["creator_id"]),
    )
    group_id = create_resp.json()["id"]

    resp = client.get(f"/api/v1/groups/{group_id}", headers=auth_headers(two_users["outsider_id"]))
    assert resp.status_code == 404


def test_only_creator_can_add_person(client, two_users):
    create_resp = client.post(
        "/api/v1/groups",
        json={"name": "Dinner Crew"},
        headers=auth_headers(two_users["creator_id"]),
    )
    group_id = create_resp.json()["id"]

    outsider_resp = client.post(
        f"/api/v1/groups/{group_id}/people",
        json={"display_name": "Sam"},
        headers=auth_headers(two_users["outsider_id"]),
    )
    assert outsider_resp.status_code == 404  # outsider can't even see the group to add to it

    creator_resp = client.post(
        f"/api/v1/groups/{group_id}/people",
        json={"display_name": "Sam"},
        headers=auth_headers(two_users["creator_id"]),
    )
    assert creator_resp.status_code == 201
    assert creator_resp.json()["display_name"] == "Sam"
    assert creator_resp.json()["supabase_user_id"] is None  # shadow contact


def test_claimed_member_can_view_but_not_manage_group(client, two_users, db_session_factory):
    create_resp = client.post(
        "/api/v1/groups",
        json={"name": "Dinner Crew"},
        headers=auth_headers(two_users["creator_id"]),
    )
    group_id = create_resp.json()["id"]

    # Manually seed a Person claimed by the "outsider" user, making them a
    # real member of the group (not the creator).
    db = db_session_factory()
    db.add(
        Person(
            id=uuid.uuid4(),
            group_id=uuid.UUID(group_id),
            supabase_user_id=two_users["outsider_id"],
            display_name="Outsider-as-member",
        )
    )
    db.commit()
    db.close()

    view_resp = client.get(
        f"/api/v1/groups/{group_id}", headers=auth_headers(two_users["outsider_id"])
    )
    assert view_resp.status_code == 200

    manage_resp = client.post(
        f"/api/v1/groups/{group_id}/people",
        json={"display_name": "New Person"},
        headers=auth_headers(two_users["outsider_id"]),
    )
    assert manage_resp.status_code == 403  # visible, but not creator - can't add/remove


def test_remove_person_from_group(client, two_users):
    create_resp = client.post(
        "/api/v1/groups",
        json={"name": "Dinner Crew"},
        headers=auth_headers(two_users["creator_id"]),
    )
    group_id = create_resp.json()["id"]
    person_resp = client.post(
        f"/api/v1/groups/{group_id}/people",
        json={"display_name": "Sam"},
        headers=auth_headers(two_users["creator_id"]),
    )
    person_id = person_resp.json()["id"]

    delete_resp = client.delete(
        f"/api/v1/groups/{group_id}/people/{person_id}",
        headers=auth_headers(two_users["creator_id"]),
    )
    assert delete_resp.status_code == 204

    get_resp = client.get(
        f"/api/v1/people/{person_id}", headers=auth_headers(two_users["creator_id"])
    )
    assert get_resp.status_code == 404


def test_list_my_groups_includes_created_and_member_groups(client, two_users, db_session_factory):
    client.post(
        "/api/v1/groups",
        json={"name": "Created By Me"},
        headers=auth_headers(two_users["creator_id"]),
    )
    other_group_resp = client.post(
        "/api/v1/groups",
        json={"name": "Someone Else's Group"},
        headers=auth_headers(two_users["outsider_id"]),
    )
    other_group_id = other_group_resp.json()["id"]

    db = db_session_factory()
    db.add(
        Person(
            id=uuid.uuid4(),
            group_id=uuid.UUID(other_group_id),
            supabase_user_id=two_users["creator_id"],
            display_name="Creator-as-member-elsewhere",
        )
    )
    db.commit()
    db.close()

    resp = client.get("/api/v1/groups", headers=auth_headers(two_users["creator_id"]))
    names = {g["name"] for g in resp.json()}
    assert names == {"Created By Me", "Someone Else's Group"}
