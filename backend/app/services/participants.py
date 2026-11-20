"""Per-bill participants (app/models/bill_participant.py): who was on a bill.

Every calculation that used to run over "everyone in the bill's group" -
predictions, the live split, persisted settlement rows - runs over the
bill's participants instead, via bill_participant_people() below.
"""

import uuid

from sqlalchemy.orm import Session

from app.models.bill import Bill
from app.models.bill_participant import BillParticipant
from app.models.person import Person


def bill_participant_people(db: Session, bill: Bill) -> list[Person]:
    """The bill's participants as Person rows, ordered by display_name (the
    same order the old group-wide queries used, so penny tie-breaks in
    app/services/splits.py stay deterministic)."""
    return (
        db.query(Person)
        .join(BillParticipant, BillParticipant.person_id == Person.id)
        .filter(BillParticipant.bill_id == bill.id)
        .order_by(Person.display_name, Person.id)
        .all()
    )


def is_participant(bill: Bill, person_id: uuid.UUID) -> bool:
    return person_id in bill.participant_person_ids


def add_participants(db: Session, bill: Bill, person_ids: list[uuid.UUID]) -> None:
    existing = set(bill.participant_person_ids)
    for person_id in person_ids:
        if person_id not in existing:
            db.add(BillParticipant(bill_id=bill.id, person_id=person_id))
            existing.add(person_id)
    db.flush()
    db.refresh(bill)
