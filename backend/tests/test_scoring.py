import uuid

import pytest

from app.models.person_taxonomy_score import PersonTaxonomyScore
from app.models.taxonomy import TaxonomySource, TaxonomyValue
from app.services.prediction.scoring import (
    NEEDS_REVIEW_CONFIDENCE_THRESHOLD,
    person_survives_hard_restrictions,
    predict_assignment,
    score_person_for_item,
)
from app.services.prediction.vectors import ItemVector, PersonVector, build_person_vector


def _row(taxonomy_value, score=0.0, is_hard_restriction=False, source=TaxonomySource.QUESTIONNAIRE):
    return PersonTaxonomyScore(
        person_id=uuid.uuid4(),
        taxonomy_value=taxonomy_value,
        score=score,
        is_hard_restriction=is_hard_restriction,
        source=source,
    )


def test_build_person_vector_only_treats_dietary_flags_as_hard_restrictions():
    rows = [
        _row(TaxonomyValue.VEGETARIAN, score=1.0, is_hard_restriction=True),
        _row(TaxonomyValue.SPICY, score=0.9, is_hard_restriction=False),
    ]
    vector = build_person_vector(rows)
    assert vector.hard_restrictions == {TaxonomyValue.VEGETARIAN}
    assert vector.score_for(TaxonomyValue.SPICY) == 0.9
    assert vector.score_for(TaxonomyValue.ENTREE) == 0.0  # untouched dimension defaults to 0


def test_vegetarian_hard_restriction_excludes_non_vegetarian_item():
    vegetarian = PersonVector(hard_restrictions={TaxonomyValue.VEGETARIAN})
    meat_dish = ItemVector(tags={TaxonomyValue.ENTREE})
    veg_dish = ItemVector(tags={TaxonomyValue.ENTREE, TaxonomyValue.VEGETARIAN})

    assert person_survives_hard_restrictions(vegetarian, meat_dish) is False
    assert person_survives_hard_restrictions(vegetarian, veg_dish) is True


def test_score_only_counts_base_type_and_flavor_dimensions_not_dietary():
    person = PersonVector(
        scores={
            TaxonomyValue.ENTREE: 0.5,
            TaxonomyValue.SPICY: 0.3,
            TaxonomyValue.VEGETARIAN: 1.0,  # dietary dim - must NOT count toward the dot product
        }
    )
    item = ItemVector(tags={TaxonomyValue.ENTREE, TaxonomyValue.SPICY, TaxonomyValue.VEGETARIAN})
    assert score_person_for_item(person, item) == pytest.approx(0.8)  # 0.5 + 0.3, not + 1.0


def test_predict_assignment_picks_landslide_winner_with_high_confidence():
    spicy_lover = uuid.uuid4()
    spicy_hater = uuid.uuid4()
    person_vectors = {
        spicy_lover: PersonVector(scores={TaxonomyValue.SPICY: 1.0, TaxonomyValue.ENTREE: 0.5}),
        spicy_hater: PersonVector(scores={TaxonomyValue.SPICY: -1.0, TaxonomyValue.ENTREE: 0.5}),
    }
    spicy_entree = ItemVector(tags={TaxonomyValue.ENTREE, TaxonomyValue.SPICY})

    result = predict_assignment(person_vectors, spicy_entree)

    assert result.winner_person_id == spicy_lover
    assert result.needs_review is False
    assert result.confidence > NEEDS_REVIEW_CONFIDENCE_THRESHOLD


def test_predict_assignment_flags_near_tie_as_needs_review():
    person_a, person_b = uuid.uuid4(), uuid.uuid4()
    person_vectors = {
        person_a: PersonVector(scores={TaxonomyValue.ENTREE: 0.51}),
        person_b: PersonVector(scores={TaxonomyValue.ENTREE: 0.50}),
    }
    item = ItemVector(tags={TaxonomyValue.ENTREE})

    result = predict_assignment(person_vectors, item)

    assert result.needs_review is True
    assert result.confidence < NEEDS_REVIEW_CONFIDENCE_THRESHOLD


def test_predict_assignment_exact_tie_forces_needs_review_regardless_of_magnitude():
    person_a, person_b = uuid.uuid4(), uuid.uuid4()
    person_vectors = {
        person_a: PersonVector(scores={TaxonomyValue.ENTREE: 0.9}),
        person_b: PersonVector(scores={TaxonomyValue.ENTREE: 0.9}),
    }
    item = ItemVector(tags={TaxonomyValue.ENTREE})

    result = predict_assignment(person_vectors, item)

    assert result.confidence == 0.0
    assert result.needs_review is True


def test_predict_assignment_single_candidate_is_full_confidence():
    person = uuid.uuid4()
    result = predict_assignment({person: PersonVector()}, ItemVector(tags={TaxonomyValue.ENTREE}))
    assert result.winner_person_id == person
    assert result.confidence == 1.0
    assert result.needs_review is False


def test_predict_assignment_all_candidates_excluded_needs_review_with_no_winner():
    vegan = uuid.uuid4()
    vegetarian = uuid.uuid4()
    person_vectors = {
        vegan: PersonVector(hard_restrictions={TaxonomyValue.VEGAN}),
        vegetarian: PersonVector(hard_restrictions={TaxonomyValue.VEGETARIAN}),
    }
    # A dish tagged vegetarian but not vegan still excludes the vegan
    # candidate; if it were tagged neither, both would be excluded.
    meat_dish = ItemVector(tags={TaxonomyValue.ENTREE})

    result = predict_assignment(person_vectors, meat_dish)

    assert result.winner_person_id is None
    assert result.needs_review is True
    assert result.all_scores == []
