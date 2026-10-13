import uuid

from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.db.session import get_db
from app.models.bill import Bill
from app.models.group import Group
from app.models.person import Person
from app.models.user import User

__all__ = [
    "get_db",
    "get_current_user",
    "get_accessible_person",
    "get_accessible_group",
    "get_accessible_bill",
    "require_group_creator",
    "user_can_access_group",
]


def user_can_access_group(group: Group, user: User, db: Session) -> bool:
    """CLAUDE.md SS9: a Person's data is only visible to Users who share a Group
    with them. A user shares a group if they created it, or if they're the
    claimed account behind one of its Person rows. Enforced here, at the API
    layer, not left to the client."""
    if group.creator_user_id == user.id:
        return True
    member = (
        db.query(Person)
        .filter(Person.group_id == group.id, Person.supabase_user_id == user.id)
        .first()
    )
    return member is not None


def get_accessible_group(
    group_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Group:
    group = db.get(Group, group_id)
    if group is None or not user_can_access_group(group, current_user, db):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group not found.")
    return group


def require_group_creator(
    group: Group = Depends(get_accessible_group),
    current_user: User = Depends(get_current_user),
) -> Group:
    """buildguide.md Block 5: group membership add/remove is creator-only.
    403 (not 404) here - the requester already cleared get_accessible_group,
    so they know this group exists; this is a real permissions boundary,
    not something to hide."""
    if group.creator_user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Only the group's creator can do this."
        )
    return group


def get_accessible_person(
    person_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Person:
    person = db.get(Person, person_id)
    if person is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Person not found.")

    group = db.get(Group, person.group_id)
    if group is None or not user_can_access_group(group, current_user, db):
        # 404 (not 403) so we don't reveal that a person/group exists at all
        # to someone with no relationship to it.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Person not found.")

    return person


def get_accessible_bill(
    bill_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Bill:
    bill = db.get(Bill, bill_id)
    if bill is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bill not found.")

    group = db.get(Group, bill.group_id)
    if group is None or not user_can_access_group(group, current_user, db):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bill not found.")

    return bill
