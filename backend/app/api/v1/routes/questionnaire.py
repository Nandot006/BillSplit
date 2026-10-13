from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_accessible_person, get_db
from app.models.person import Person
from app.schemas.person_taxonomy_score import PersonTaxonomyScoreOut
from app.schemas.questionnaire import QuestionnaireSubmission
from app.services.questionnaire import apply_questionnaire

router = APIRouter()


@router.post("/people/{person_id}/questionnaire", response_model=list[PersonTaxonomyScoreOut])
def submit_questionnaire(
    answers: QuestionnaireSubmission,
    person: Person = Depends(get_accessible_person),
    db: Session = Depends(get_db),
):
    """Applies a completed cold-start questionnaire to a Person, seeding/
    updating their PersonTaxonomyScore rows (design.md SS4). Safe to call
    again later (e.g. the user goes back and changes an answer) - re-submitting
    updates existing questionnaire-sourced rows in place rather than
    duplicating them, and never overwrites a dimension that's since been
    adjusted by a real learned_correction."""
    if answers.additional_preferences is not None:
        person.free_text_preferences = answers.additional_preferences

    rows = apply_questionnaire(db, person.id, answers)
    db.commit()
    for row in rows:
        db.refresh(row)
    return rows
