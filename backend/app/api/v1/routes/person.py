from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_accessible_person, get_db
from app.models.person import Person
from app.schemas.person import PersonOut, PersonUpdate

router = APIRouter()


@router.get("/people/{person_id}", response_model=PersonOut)
def get_person(person: Person = Depends(get_accessible_person)):
    """View a Person's profile. Covers both a shadow contact's stored
    preferences and a claimed account's own profile (design.md SS2)."""
    return person


@router.patch("/people/{person_id}", response_model=PersonOut)
def update_person(
    updates: PersonUpdate,
    person: Person = Depends(get_accessible_person),
    db: Session = Depends(get_db),
):
    """Edit a Person's display name / free-text preferences. Adding or
    removing a Person from a Group is Backend Block 5's job, not this one -
    see app/models/group.py's docstring."""
    for field, value in updates.model_dump(exclude_unset=True).items():
        setattr(person, field, value)
    db.commit()
    db.refresh(person)
    return person
