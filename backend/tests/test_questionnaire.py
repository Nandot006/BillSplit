import uuid

import pytest

from app.models.group import Group
from app.models.person import Person
from app.models.person_taxonomy_score import PersonTaxonomyScore
from app.models.taxonomy import TaxonomySource, TaxonomyValue
from app.models.user import User
from tests.auth_helpers import auth_headers

CORE_ANSWERS = {
    "vegetarian_or_vegan": "none",
    "avoids_gluten": False,
    "avoids_dairy": False,
    "has_nut_allergy": False,
    "avoids_pork": False,
    "avoids_beef": False,
    "drinks_alcohol": True,
    "appetizer_frequency": 0.5,
    "entree_vs_shared_preference": 0.8,
    "spice_tolerance": -0.2,
    "dessert_frequency": 0.6,
    "savory_vs_sweet_preference": 0.4,
}


@pytest.fixture()
def seeded(db_session_factory):
    db = db_session_factory()
    creator = User(id=uuid.uuid4(), email="creator@example.com")
    outsider = User(id=uuid.uuid4(), email="outsider@example.com")
    db.add_all([creator, outsider])
    db.flush()
    group = Group(id=uuid.uuid4(), name="G", creator_user_id=creator.id)
    db.add(group)
    db.flush()
    person = Person(id=uuid.uuid4(), group_id=group.id, display_name="Alex")
    db.add(person)
    db.commit()
    ids = {"creator_id": creator.id, "outsider_id": outsider.id, "person_id": person.id}
    db.close()
    return ids


def _scores_by_value(db_session_factory, person_id):
    db = db_session_factory()
    rows = db.query(PersonTaxonomyScore).filter(PersonTaxonomyScore.person_id == person_id).all()
    result = {row.taxonomy_value: row for row in rows}
    db.close()
    return result


def test_core_answers_seed_expected_dimensions(client, seeded, db_session_factory):
    resp = client.post(
        f"/api/v1/people/{seeded['person_id']}/questionnaire",
        json=CORE_ANSWERS,
        headers=auth_headers(seeded["creator_id"]),
    )
    assert resp.status_code == 200

    scores = _scores_by_value(db_session_factory, seeded["person_id"])

    # Q7: drinks_alcohol=True -> affinity, not a hard restriction; no NO_ALCOHOL row.
    assert scores[TaxonomyValue.DRINK_ALCOHOLIC].score == pytest.approx(0.7)
    assert scores[TaxonomyValue.DRINK_ALCOHOLIC].is_hard_restriction is False
    assert TaxonomyValue.NO_ALCOHOL not in scores

    # Q9: entree_vs_shared_preference=0.8 -> ENTREE gets +0.8, SHARED_PLATTER gets -0.8.
    assert scores[TaxonomyValue.ENTREE].score == pytest.approx(0.8)
    assert scores[TaxonomyValue.SHARED_PLATTER].score == pytest.approx(-0.8)

    # Q11 + Q12 both touch SWEET: dessert=0.6, -(savory_vs_sweet=0.4)=-0.4 -> avg = 0.1
    assert scores[TaxonomyValue.SWEET].score == pytest.approx(0.1)
    assert scores[TaxonomyValue.DESSERT].score == pytest.approx(0.6)
    assert scores[TaxonomyValue.SAVORY].score == pytest.approx(0.4)

    for value in scores.values():
        assert value.source == TaxonomySource.QUESTIONNAIRE


def test_vegan_sets_both_vegetarian_and_vegan_hard_restrictions(client, seeded, db_session_factory):
    answers = {**CORE_ANSWERS, "vegetarian_or_vegan": "vegan"}
    resp = client.post(
        f"/api/v1/people/{seeded['person_id']}/questionnaire",
        json=answers,
        headers=auth_headers(seeded["creator_id"]),
    )
    assert resp.status_code == 200
    scores = _scores_by_value(db_session_factory, seeded["person_id"])
    assert scores[TaxonomyValue.VEGETARIAN].is_hard_restriction is True
    assert scores[TaxonomyValue.VEGAN].is_hard_restriction is True


def test_no_alcohol_sets_hard_restriction_not_affinity(client, seeded, db_session_factory):
    answers = {**CORE_ANSWERS, "drinks_alcohol": False}
    resp = client.post(
        f"/api/v1/people/{seeded['person_id']}/questionnaire",
        json=answers,
        headers=auth_headers(seeded["creator_id"]),
    )
    assert resp.status_code == 200
    scores = _scores_by_value(db_session_factory, seeded["person_id"])
    assert scores[TaxonomyValue.NO_ALCOHOL].is_hard_restriction is True
    assert TaxonomyValue.DRINK_ALCOHOLIC not in scores


def test_resubmission_updates_in_place_without_duplicating(client, seeded, db_session_factory):
    client.post(
        f"/api/v1/people/{seeded['person_id']}/questionnaire",
        json=CORE_ANSWERS,
        headers=auth_headers(seeded["creator_id"]),
    )
    updated_answers = {**CORE_ANSWERS, "appetizer_frequency": -1.0}
    client.post(
        f"/api/v1/people/{seeded['person_id']}/questionnaire",
        json=updated_answers,
        headers=auth_headers(seeded["creator_id"]),
    )

    db = db_session_factory()
    rows = (
        db.query(PersonTaxonomyScore)
        .filter(
            PersonTaxonomyScore.person_id == seeded["person_id"],
            PersonTaxonomyScore.taxonomy_value == TaxonomyValue.APPETIZER,
        )
        .all()
    )
    db.close()
    assert len(rows) == 1
    assert rows[0].score == pytest.approx(-1.0)


def test_resubmission_does_not_overwrite_a_learned_correction(client, seeded, db_session_factory):
    db = db_session_factory()
    db.add(
        PersonTaxonomyScore(
            person_id=seeded["person_id"],
            taxonomy_value=TaxonomyValue.SPICY,
            score=0.99,
            is_hard_restriction=False,
            source=TaxonomySource.LEARNED_CORRECTION,
            correction_count=3,
        )
    )
    db.commit()
    db.close()

    client.post(
        f"/api/v1/people/{seeded['person_id']}/questionnaire",
        json=CORE_ANSWERS,
        headers=auth_headers(seeded["creator_id"]),
    )

    scores = _scores_by_value(db_session_factory, seeded["person_id"])
    assert scores[TaxonomyValue.SPICY].score == pytest.approx(0.99)
    assert scores[TaxonomyValue.SPICY].source == TaxonomySource.LEARNED_CORRECTION


def test_additional_preferences_sets_free_text(client, seeded):
    answers = {**CORE_ANSWERS, "additional_preferences": "hates cilantro"}
    resp = client.post(
        f"/api/v1/people/{seeded['person_id']}/questionnaire",
        json=answers,
        headers=auth_headers(seeded["creator_id"]),
    )
    assert resp.status_code == 200
    person_resp = client.get(
        f"/api/v1/people/{seeded['person_id']}", headers=auth_headers(seeded["creator_id"])
    )
    assert person_resp.json()["free_text_preferences"] == "hates cilantro"


def test_outsider_cannot_submit_questionnaire(client, seeded):
    resp = client.post(
        f"/api/v1/people/{seeded['person_id']}/questionnaire",
        json=CORE_ANSWERS,
        headers=auth_headers(seeded["outsider_id"]),
    )
    assert resp.status_code == 404
