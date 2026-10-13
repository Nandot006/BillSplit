import uuid

from sqlalchemy.orm import Session

from app.models.person_taxonomy_score import PersonTaxonomyScore
from app.models.taxonomy import TaxonomySource, TaxonomyValue
from app.schemas.questionnaire import QuestionnaireSubmission


def _upsert_score(
    db: Session,
    person_id: uuid.UUID,
    taxonomy_value: TaxonomyValue,
    score: float,
    is_hard_restriction: bool,
) -> PersonTaxonomyScore:
    existing = (
        db.query(PersonTaxonomyScore)
        .filter(
            PersonTaxonomyScore.person_id == person_id,
            PersonTaxonomyScore.taxonomy_value == taxonomy_value,
        )
        .first()
    )
    if existing is not None:
        if existing.source == TaxonomySource.LEARNED_CORRECTION:
            # Don't let a re-submitted questionnaire clobber what's already
            # been learned from real corrections on this dimension.
            return existing
        existing.score = score
        existing.is_hard_restriction = is_hard_restriction
        return existing

    row = PersonTaxonomyScore(
        person_id=person_id,
        taxonomy_value=taxonomy_value,
        score=score,
        is_hard_restriction=is_hard_restriction,
        source=TaxonomySource.QUESTIONNAIRE,
    )
    db.add(row)
    return row


def apply_questionnaire(
    db: Session, person_id: uuid.UUID, answers: QuestionnaireSubmission
) -> list[PersonTaxonomyScore]:
    """Seeds/updates PersonTaxonomyScore rows for a Person from a completed
    cold-start questionnaire (design.md SS4). See QuestionnaireSubmission's
    docstring for the field -> taxonomy-value mapping used here."""

    hard_restrictions: dict[TaxonomyValue, bool] = {}
    preference_contributions: dict[TaxonomyValue, list[float]] = {}

    def add_preference(value: TaxonomyValue, score: float | None) -> None:
        if score is not None:
            preference_contributions.setdefault(value, []).append(score)

    # Q1
    if answers.vegetarian_or_vegan in ("vegetarian", "vegan"):
        hard_restrictions[TaxonomyValue.VEGETARIAN] = True
    if answers.vegetarian_or_vegan == "vegan":
        hard_restrictions[TaxonomyValue.VEGAN] = True

    # Q2-6
    if answers.avoids_gluten:
        hard_restrictions[TaxonomyValue.GLUTEN_FREE] = True
    if answers.avoids_dairy:
        hard_restrictions[TaxonomyValue.DAIRY_FREE] = True
    if answers.has_nut_allergy:
        hard_restrictions[TaxonomyValue.NUT_FREE] = True
    if answers.avoids_pork:
        hard_restrictions[TaxonomyValue.NO_PORK] = True
    if answers.avoids_beef:
        hard_restrictions[TaxonomyValue.NO_BEEF] = True

    # Q7 - one branch or the other, never both
    if answers.drinks_alcohol:
        add_preference(TaxonomyValue.DRINK_ALCOHOLIC, 0.7)
    else:
        hard_restrictions[TaxonomyValue.NO_ALCOHOL] = True

    # Q8-12
    add_preference(TaxonomyValue.APPETIZER, answers.appetizer_frequency)
    add_preference(TaxonomyValue.ENTREE, answers.entree_vs_shared_preference)
    add_preference(TaxonomyValue.SHARED_PLATTER, -answers.entree_vs_shared_preference)
    add_preference(TaxonomyValue.SPICY, answers.spice_tolerance)
    add_preference(TaxonomyValue.DESSERT, answers.dessert_frequency)
    add_preference(TaxonomyValue.SWEET, answers.dessert_frequency)
    add_preference(TaxonomyValue.SAVORY, answers.savory_vs_sweet_preference)
    add_preference(TaxonomyValue.SWEET, -answers.savory_vs_sweet_preference)

    # Q13-16 (optional)
    add_preference(TaxonomyValue.DRINK_NON_ALCOHOLIC, answers.non_alcoholic_drink_frequency)
    add_preference(TaxonomyValue.SOUR, answers.sour_preference)
    add_preference(TaxonomyValue.MILD, answers.mild_preference)
    add_preference(TaxonomyValue.SIDE, answers.side_frequency)

    rows: list[PersonTaxonomyScore] = []
    for value, is_hard in hard_restrictions.items():
        rows.append(_upsert_score(db, person_id, value, score=1.0, is_hard_restriction=is_hard))
    for value, scores in preference_contributions.items():
        rows.append(
            _upsert_score(
                db, person_id, value, score=sum(scores) / len(scores), is_hard_restriction=False
            )
        )

    return rows
