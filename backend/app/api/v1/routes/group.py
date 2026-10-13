import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_accessible_group, get_current_user, get_db, require_group_creator
from app.models.bill import Bill, BillStatus
from app.models.bill_item import BillItem
from app.models.bill_item_assignment import BillItemAssignment
from app.models.group import Group
from app.models.payer_history import PayerHistory
from app.models.person import Person
from app.models.user import User
from app.schemas.group import AddPersonToGroup, GroupCreate, GroupDetailOut, GroupOut, GroupUpdate
from app.schemas.payer import PayerSuggestionOut
from app.schemas.person import PersonOut
from app.services.payer import suggest_payer
from app.services.prediction.pipeline import redistribute_bill_after_person_removal

router = APIRouter()


@router.post("/groups", response_model=GroupOut, status_code=status.HTTP_201_CREATED)
def create_group(
    body: GroupCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    group = Group(name=body.name, creator_user_id=current_user.id)
    db.add(group)
    db.commit()
    db.refresh(group)
    return group


@router.get("/groups", response_model=list[GroupOut])
def list_my_groups(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Groups the current user created, plus groups where they're the
    claimed account behind one of its Person rows."""
    created = db.query(Group).filter(Group.creator_user_id == current_user.id).all()
    member_group_ids = (
        db.query(Person.group_id)
        .filter(Person.supabase_user_id == current_user.id)
        .scalar_subquery()
    )
    member = db.query(Group).filter(Group.id.in_(member_group_ids)).all()

    groups = {g.id: g for g in created}
    for g in member:
        groups.setdefault(g.id, g)
    return list(groups.values())


@router.get("/groups/{group_id}", response_model=GroupDetailOut)
def get_group(group: Group = Depends(get_accessible_group)):
    return group


@router.patch("/groups/{group_id}", response_model=GroupOut)
def update_group(
    body: GroupUpdate,
    group: Group = Depends(require_group_creator),
    db: Session = Depends(get_db),
):
    group.name = body.name
    db.commit()
    db.refresh(group)
    return group


@router.delete("/groups/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_group(
    group: Group = Depends(require_group_creator),
    db: Session = Depends(get_db),
):
    db.delete(group)
    db.commit()


@router.get("/groups/{group_id}/payer-suggestion", response_model=PayerSuggestionOut)
def get_payer_suggestion(
    group: Group = Depends(get_accessible_group),
    db: Session = Depends(get_db),
):
    """buildguide.md Backend Block 11 / design.md SS11: who a payer
    dropdown should default to for this group's next bill - least
    recently paid, never-paid first, alphabetical tie-break
    (app/services/payer.suggest_payer). Always overridable client-side;
    this endpoint only supplies the default. 404s if the group has no
    people yet - there's no one to suggest."""
    person = suggest_payer(db, group.id)
    if person is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Group has no people to suggest as payer.",
        )
    history = db.get(PayerHistory, (group.id, person.id))
    return PayerSuggestionOut(
        person_id=person.id,
        display_name=person.display_name,
        payment_count=history.payment_count if history else 0,
        last_paid_at=history.last_paid_at if history else None,
    )


@router.post(
    "/groups/{group_id}/people", response_model=PersonOut, status_code=status.HTTP_201_CREATED
)
def add_person_to_group(
    body: AddPersonToGroup,
    group: Group = Depends(require_group_creator),
    db: Session = Depends(get_db),
):
    """Creator-only (buildguide.md Block 5). Adds a shadow contact to the
    group - there's no invite/claim flow yet to link this Person to a real
    User account; that's a future addition, not built in v1."""
    person = Person(
        group_id=group.id,
        display_name=body.display_name,
        free_text_preferences=body.free_text_preferences,
    )
    db.add(person)
    db.commit()
    db.refresh(person)
    return person


@router.delete("/groups/{group_id}/people/{person_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_person_from_group(
    person_id: uuid.UUID,
    group: Group = Depends(require_group_creator),
    db: Session = Depends(get_db),
):
    """Creator-only (buildguide.md Block 5). Backend Block 10 resolves the
    note that used to sit here: hard-deleting a Person cascades away their
    BillItemAssignment/PredictionFeedback rows (see those models'
    ondelete settings), which would silently erase history from a closed
    bill - violating design.md SS12's "closed bills are fully immutable."
    So this endpoint now does two things design.md doesn't spell out in
    that much detail but that follow directly from SS9/SS12:

    1. Blocked (409) if the person has any item assignment, or was the
       recorded payer, on a bill that's already CLOSED for this group -
       that history has to survive exactly as it is. design.md doesn't
       offer a third option (e.g. a "removed but retained for history"
       state), so this is a deliberate stop rather than a guess at one -
       worth revisiting explicitly if it turns out to matter in practice.
    2. Otherwise, for every one of the group's bills that isn't CLOSED,
       redistribute_bill_after_person_removal() re-scores any item this
       person was the sole assignee of against the remaining people, and
       re-normalizes the share on any item they shared with others -
       *before* the Person row (and its now-empty assignments) are
       actually deleted. A bill that ends up with an item nobody could be
       re-scored onto (e.g. a hard restriction excludes every remaining
       person) drops back from open to needs_review, same as any other
       bill with an unassigned item - a human finishes it by hand via the
       existing PUT .../assign endpoint.
    """
    person = db.get(Person, person_id)
    if person is None or person.group_id != group.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Person not found in this group."
        )

    closed_bill_ids = [
        row.id
        for row in db.query(Bill.id).filter(
            Bill.group_id == group.id, Bill.status == BillStatus.CLOSED
        )
    ]
    has_closed_assignment = False
    has_closed_payer_role = False
    if closed_bill_ids:
        has_closed_assignment = (
            db.query(BillItemAssignment)
            .join(BillItem, BillItemAssignment.bill_item_id == BillItem.id)
            .filter(
                BillItemAssignment.person_id == person_id,
                BillItem.bill_id.in_(closed_bill_ids),
            )
            .first()
            is not None
        )
        has_closed_payer_role = (
            db.query(Bill)
            .filter(Bill.id.in_(closed_bill_ids), Bill.payer_person_id == person_id)
            .first()
            is not None
        )
    if has_closed_assignment or has_closed_payer_role:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Cannot remove a person with history on a closed bill - "
                "closed bills must stay immutable."
            ),
        )

    active_bills = (
        db.query(Bill).filter(Bill.group_id == group.id, Bill.status != BillStatus.CLOSED).all()
    )
    for bill in active_bills:
        left_something_unassigned = redistribute_bill_after_person_removal(db, bill, person_id)
        if left_something_unassigned and bill.status == BillStatus.OPEN:
            bill.status = BillStatus.NEEDS_REVIEW

    db.delete(person)
    db.commit()
