"""Shared helpers for tests that build Bills directly through the ORM.

Since bills track their own participants (app/models/bill_participant.py),
a Bill created straight in the DB has nobody on it until participants are
added - the API's create_bill does this itself, ORM-level tests do it here.
"""

from sqlalchemy.orm import Session

from app.models.bill import Bill
from app.models.person import Person
from app.services.participants import add_participants


def add_whole_group_as_participants(db: Session, bill: Bill) -> None:
    """Puts every current member of the bill's group on the bill - the same
    default the API uses when participant_person_ids is omitted."""
    people = db.query(Person).filter(Person.group_id == bill.group_id).all()
    add_participants(db, bill, [p.id for p in people])
