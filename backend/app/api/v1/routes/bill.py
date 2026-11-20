import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_accessible_bill, get_accessible_group, get_current_user, get_db
from app.models.bill import Bill, BillStatus
from app.models.bill_item import BillItem
from app.models.bill_item_tags import BillItemDietaryFlag, BillItemFlavorTag
from app.models.bill_participant import BillParticipant
from app.models.group import Group
from app.models.payer_history import PayerHistory
from app.models.person import Person
from app.models.user import User
from app.schemas.bill import (
    BillCreate,
    BillDetailOut,
    BillImageUrlOut,
    BillOut,
    BillParticipantAdd,
    BillUpdate,
)
from app.schemas.bill_item import (
    AssignItemRequest,
    BillItemCreate,
    BillItemOut,
    BillItemUpdate,
    SetAssigneesRequest,
    bill_item_out_from_model,
)
from app.schemas.payer import PayerSuggestionOut, SetBillPayer
from app.schemas.split import PersonSplitOut, SetSplitPaid, SplitOut, split_out_from_model
from app.services.bills import recompute_bill_totals
from app.services.ocr.pipeline import run_bill_processing_job
from app.services.participants import add_participants, bill_participant_people
from app.services.payer import record_payer_change, suggest_payer
from app.services.prediction.pipeline import (
    generate_predictions_for_bill,
    record_correction,
    redistribute_bill_after_person_removal,
    set_item_assignees,
)
from app.services.settlement import ensure_settlement_rows, get_split_for_person, sync_bill_splits
from app.services.splits import compute_bill_splits
from app.services.storage import StorageError, create_signed_image_url

router = APIRouter()

# Decision 2026-11-20: items can be added, edited and removed while a bill
# is being entered by hand *or* reviewed after OCR (to fix misreads) - but
# not once it's open, since settlement amounts are built on them from then.
_ITEM_EDITABLE_STATUSES = (BillStatus.NEEDS_MANUAL_ENTRY, BillStatus.NEEDS_REVIEW)
_ASSIGNABLE_STATUSES = (BillStatus.NEEDS_REVIEW, BillStatus.OPEN)


def _bill_out(bill: Bill) -> BillOut:
    return BillOut.model_validate(bill)


def _require_not_closed(bill: Bill) -> None:
    if bill.status == BillStatus.CLOSED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Bill is closed and immutable."
        )


def _require_item_editable(bill: Bill) -> None:
    if bill.status not in _ITEM_EDITABLE_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Items can only be changed while the bill is in needs_manual_entry or "
            "needs_review.",
        )


def _get_item(db: Session, bill: Bill, item_id: uuid.UUID) -> BillItem:
    item = db.get(BillItem, item_id)
    if item is None or item.bill_id != bill.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Item not found on this bill."
        )
    return item


def _require_participants(bill: Bill, person_ids: list[uuid.UUID]) -> None:
    on_bill = set(bill.participant_person_ids)
    if any(person_id not in on_bill for person_id in person_ids):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Every person must be a participant on this bill.",
        )


def _set_item_tags(
    db: Session, item: BillItem, flavor_tags: list | None, dietary_flags: list | None
) -> None:
    if flavor_tags is not None:
        for row in list(item.flavor_tags):
            db.delete(row)
        db.flush()
        for tag in dict.fromkeys(flavor_tags):
            db.add(BillItemFlavorTag(bill_item_id=item.id, flavor_tag=tag))
    if dietary_flags is not None:
        for flag_row in list(item.dietary_flags):
            db.delete(flag_row)
        db.flush()
        for flag in dict.fromkeys(dietary_flags):
            db.add(BillItemDietaryFlag(bill_item_id=item.id, dietary_flag=flag))


@router.post(
    "/groups/{group_id}/bills", response_model=BillOut, status_code=status.HTTP_201_CREATED
)
def create_bill(
    body: BillCreate,
    background_tasks: BackgroundTasks,
    group: Group = Depends(get_accessible_group),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Any group member can start a bill (unlike group membership, which is
    creator-only - see get_accessible_group vs require_group_creator).
    image_storage_path present -> PROCESSING, and the OCR -> taxonomy ->
    prediction pipeline is queued as a background task so this request
    doesn't block on it (CLAUDE.md SS8); absent -> NEEDS_MANUAL_ENTRY.

    The image path must sit in the caller's own Storage folder
    ("<user id>/..."), which is the only place Storage's access policy lets
    them upload. Otherwise someone could point a bill at another user's
    receipt and read it back through OCR or the image URL endpoint."""
    if body.image_storage_path is not None and not body.image_storage_path.startswith(
        f"{current_user.id}/"
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="image_storage_path must be inside your own upload folder.",
        )

    group_person_ids = [p.id for p in group.people]
    if body.participant_person_ids is None:
        participant_ids = group_person_ids
    else:
        participant_ids = list(dict.fromkeys(body.participant_person_ids))
        if any(pid not in group_person_ids for pid in participant_ids):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Every participant must belong to this bill's group.",
            )
    if not participant_ids:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="A bill needs at least one participant.",
        )

    initial_status = (
        BillStatus.PROCESSING if body.image_storage_path else BillStatus.NEEDS_MANUAL_ENTRY
    )
    bill = Bill(
        group_id=group.id,
        image_storage_path=body.image_storage_path,
        merchant_name=body.merchant_name,
        bill_date=body.bill_date,
        status=initial_status,
    )
    db.add(bill)
    db.flush()
    add_participants(db, bill, participant_ids)
    db.commit()
    db.refresh(bill)

    if bill.status == BillStatus.PROCESSING:
        background_tasks.add_task(run_bill_processing_job, bill.id)

    return _bill_out(bill)


@router.get("/groups/{group_id}/bills", response_model=list[BillOut])
def list_group_bills(group: Group = Depends(get_accessible_group), db: Session = Depends(get_db)):
    bills = db.query(Bill).filter(Bill.group_id == group.id).order_by(Bill.created_at.desc()).all()
    return [_bill_out(bill) for bill in bills]


@router.get("/bills/{bill_id}", response_model=BillDetailOut)
def get_bill(bill: Bill = Depends(get_accessible_bill)):
    return BillDetailOut(
        **_bill_out(bill).model_dump(),
        items=[bill_item_out_from_model(item) for item in bill.items],
    )


@router.patch("/bills/{bill_id}", response_model=BillOut)
def update_bill(
    body: BillUpdate,
    bill: Bill = Depends(get_accessible_bill),
    db: Session = Depends(get_db),
):
    _require_not_closed(bill)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(bill, field, value)
    recompute_bill_totals(bill)
    db.commit()
    db.refresh(bill)
    return _bill_out(bill)


@router.delete("/bills/{bill_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_bill(bill: Bill = Depends(get_accessible_bill), db: Session = Depends(get_db)):
    """Discard a bill that hasn't been settled yet - a wrong photo, a
    duplicate, a test. Closed bills are settled history (design.md SS12)
    and can't be deleted."""
    _require_not_closed(bill)
    db.delete(bill)
    db.commit()


@router.get("/bills/{bill_id}/image-url", response_model=BillImageUrlOut)
def get_bill_image_url(bill: Bill = Depends(get_accessible_bill)):
    if not bill.image_storage_path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bill has no image.")
    expires_in = 600
    try:
        url = create_signed_image_url(bill.image_storage_path, expires_in=expires_in)
    except StorageError:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail="Could not load the receipt image."
        )
    return BillImageUrlOut(url=url, expires_in=expires_in)


@router.post("/bills/{bill_id}/switch-to-manual-entry", response_model=BillOut)
def switch_to_manual_entry(
    bill: Bill = Depends(get_accessible_bill), db: Session = Depends(get_db)
):
    """design.md SS13: manual entry is always available on a bill stuck in
    processing. If the OCR job finishes later, it sees the bill is no
    longer processing and discards its result
    (app/services/ocr/pipeline.process_bill)."""
    if bill.status != BillStatus.PROCESSING:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Bill is not processing.")
    bill.status = BillStatus.NEEDS_MANUAL_ENTRY
    db.commit()
    db.refresh(bill)
    return _bill_out(bill)


# --- participants ------------------------------------------------------------


@router.post("/bills/{bill_id}/participants", response_model=BillOut)
def add_bill_participant(
    body: BillParticipantAdd,
    bill: Bill = Depends(get_accessible_bill),
    db: Session = Depends(get_db),
):
    """Adds a group member to this bill. Existing item assignments don't
    change; they now share the tax/tip split. Adding someone already on the
    bill is a no-op."""
    _require_not_closed(bill)
    person = db.get(Person, body.person_id)
    if person is None or person.group_id != bill.group_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="person_id must belong to this bill's group.",
        )
    add_participants(db, bill, [person.id])
    if bill.status == BillStatus.OPEN:
        sync_bill_splits(db, bill)
    db.commit()
    db.refresh(bill)
    return _bill_out(bill)


@router.delete("/bills/{bill_id}/participants/{person_id}", response_model=BillOut)
def remove_bill_participant(
    person_id: uuid.UUID,
    bill: Bill = Depends(get_accessible_bill),
    db: Session = Depends(get_db),
):
    """Removes someone from just this bill (design.md SS9). Items they had
    to themselves are re-scored against the remaining participants; shared
    items re-split among whoever's left; tax and tip re-split evenly. If an
    item can't be re-scored onto anyone (hard restrictions), an open bill
    drops back to needs_review for a human to assign it.

    The payer can be removed as a participant and stay the payer - someone
    can pay for a meal they didn't eat."""
    _require_not_closed(bill)
    participant = db.get(BillParticipant, (bill.id, person_id))
    if participant is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Person is not on this bill."
        )
    if len(bill.participants) <= 1:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="A bill needs at least one participant.",
        )

    left_something_unassigned = redistribute_bill_after_person_removal(db, bill, person_id)
    db.delete(participant)
    db.flush()
    db.refresh(bill)
    if left_something_unassigned and bill.status == BillStatus.OPEN:
        bill.status = BillStatus.NEEDS_REVIEW
    if bill.status == BillStatus.OPEN:
        sync_bill_splits(db, bill)
    db.commit()
    db.refresh(bill)
    return _bill_out(bill)


# --- items -------------------------------------------------------------------


@router.post(
    "/bills/{bill_id}/items", response_model=BillItemOut, status_code=status.HTTP_201_CREATED
)
def add_bill_item(
    body: BillItemCreate,
    bill: Bill = Depends(get_accessible_bill),
    db: Session = Depends(get_db),
):
    """Manual item entry - the OCR-failure fallback (Backend Block 7), and,
    during review, adding a line OCR missed. An item added during review is
    run through the scorer straight away so it arrives with a prediction
    like every other item."""
    _require_item_editable(bill)
    item = BillItem(
        bill_id=bill.id,
        parsed_name=body.parsed_name,
        price=body.price,
        quantity=body.quantity,
        base_type=body.base_type,
    )
    db.add(item)
    db.flush()
    _set_item_tags(db, item, body.flavor_tags, body.dietary_flags)
    db.flush()
    db.refresh(bill)
    recompute_bill_totals(bill)
    if bill.status == BillStatus.NEEDS_REVIEW:
        db.refresh(item)
        generate_predictions_for_bill(db, bill)
    db.commit()
    db.refresh(item)
    return bill_item_out_from_model(item)


@router.patch("/bills/{bill_id}/items/{item_id}", response_model=BillItemOut)
def update_bill_item(
    item_id: uuid.UUID,
    body: BillItemUpdate,
    bill: Bill = Depends(get_accessible_bill),
    db: Session = Depends(get_db),
):
    """Fix an item's name, price, quantity or tags (decision 2026-11-20).
    Doesn't touch who it's assigned to - re-tagging an item isn't a
    correction of the prediction, so it produces no learning signal."""
    _require_item_editable(bill)
    item = _get_item(db, bill, item_id)
    updates = body.model_dump(exclude_unset=True)
    for field in ("parsed_name", "price", "quantity", "base_type"):
        if field in updates:
            if field != "base_type" and updates[field] is None:
                continue  # these columns are NOT NULL; null means "leave as is"
            setattr(item, field, updates[field])
    _set_item_tags(db, item, updates.get("flavor_tags"), updates.get("dietary_flags"))
    db.flush()
    db.refresh(bill)
    recompute_bill_totals(bill)
    db.commit()
    db.refresh(item)
    return bill_item_out_from_model(item)


@router.delete("/bills/{bill_id}/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_bill_item(
    item_id: uuid.UUID,
    bill: Bill = Depends(get_accessible_bill),
    db: Session = Depends(get_db),
):
    _require_item_editable(bill)
    item = _get_item(db, bill, item_id)
    db.delete(item)
    db.flush()
    db.refresh(bill)
    recompute_bill_totals(bill)
    db.commit()


@router.post("/bills/{bill_id}/finalize-manual-entry", response_model=BillOut)
def finalize_manual_entry(
    bill: Bill = Depends(get_accessible_bill),
    db: Session = Depends(get_db),
):
    """Moves a hand-entered bill from needs_manual_entry to needs_review,
    running the scorer over its items first (a manually-entered item can
    carry base_type/flavor/dietary tags just like an OCR'd one). Items left
    untagged simply get no prediction and wait for a manual assignment."""
    if bill.status != BillStatus.NEEDS_MANUAL_ENTRY:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Bill is not in needs_manual_entry."
        )
    if not bill.items:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Add at least one item first."
        )
    generate_predictions_for_bill(db, bill)
    bill.status = BillStatus.NEEDS_REVIEW
    db.commit()
    db.refresh(bill)
    return _bill_out(bill)


@router.put("/bills/{bill_id}/items/{item_id}/assign", response_model=BillItemOut)
def assign_bill_item(
    item_id: uuid.UUID,
    body: AssignItemRequest,
    bill: Bill = Depends(get_accessible_bill),
    db: Session = Depends(get_db),
):
    """The confirm/correct action (PRD SS5 step 4, design.md SS8): sets an
    item's sole assignee, capturing a learned_correction signal whenever
    this actually changes who the item is assigned to. Available in
    needs_review and open ("editable until finalized", CLAUDE.md SS8),
    never once the bill is closed."""
    return _apply_assignees(db, bill, item_id, [body.person_id])


@router.put("/bills/{bill_id}/items/{item_id}/assignees", response_model=BillItemOut)
def set_bill_item_assignees(
    item_id: uuid.UUID,
    body: SetAssigneesRequest,
    bill: Bill = Depends(get_accessible_bill),
    db: Session = Depends(get_db),
):
    """Shared items (design.md SS7): set everyone who had this item; its cost
    splits evenly between them. See set_item_assignees for the learning
    signal this records."""
    return _apply_assignees(db, bill, item_id, body.person_ids)


def _apply_assignees(
    db: Session, bill: Bill, item_id: uuid.UUID, person_ids: list[uuid.UUID]
) -> BillItemOut:
    if bill.status not in _ASSIGNABLE_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Items can only be (re)assigned while the bill is in needs_review or open.",
        )
    item = _get_item(db, bill, item_id)
    _require_participants(bill, person_ids)

    if len(set(person_ids)) == 1:
        record_correction(db, item, person_ids[0])
    else:
        set_item_assignees(db, item, person_ids)
    # Backend Block 12: once a bill is open, an assignment change shifts who
    # owes what, so keep the persisted Split rows current.
    if bill.status == BillStatus.OPEN:
        sync_bill_splits(db, bill)
    db.commit()
    db.refresh(item)
    return bill_item_out_from_model(item)


@router.post("/bills/{bill_id}/confirm", response_model=BillOut)
def confirm_bill(
    bill: Bill = Depends(get_accessible_bill),
    db: Session = Depends(get_db),
):
    """Moves a bill from needs_review to open once every item has at least
    one assignment. Creates the persisted Split rows (one per participant)."""
    if bill.status != BillStatus.NEEDS_REVIEW:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Bill is not in needs_review."
        )
    unassigned = [item for item in bill.items if not item.assignments]
    if unassigned:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"{len(unassigned)} item(s) still need a manual assignment.",
        )
    bill.status = BillStatus.OPEN
    sync_bill_splits(db, bill)
    db.commit()
    db.refresh(bill)
    return _bill_out(bill)


# --- payer, splits, settlement, closing --------------------------------------


@router.get("/bills/{bill_id}/payer-suggestion", response_model=PayerSuggestionOut)
def get_bill_payer_suggestion(
    bill: Bill = Depends(get_accessible_bill), db: Session = Depends(get_db)
):
    """design.md SS11's prefill, limited to this bill's participants (the
    group-level GET /groups/{id}/payer-suggestion considers everyone)."""
    person = suggest_payer(db, bill.group_id, candidate_ids=bill.participant_person_ids)
    if person is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Bill has no participants."
        )
    history = db.get(PayerHistory, (bill.group_id, person.id))
    return PayerSuggestionOut(
        person_id=person.id,
        display_name=person.display_name,
        payment_count=history.payment_count if history else 0,
        last_paid_at=history.last_paid_at if history else None,
    )


@router.put("/bills/{bill_id}/payer", response_model=BillOut)
def set_bill_payer(
    body: SetBillPayer,
    bill: Bill = Depends(get_accessible_bill),
    db: Session = Depends(get_db),
):
    """Sets (or clears, with person_id = None) who fronted the money for this
    bill, recorded into PayerHistory for future prefill (design.md SS11).
    Any group member can be the payer, even one who isn't a participant."""
    _require_not_closed(bill)
    if body.person_id is not None:
        person = db.get(Person, body.person_id)
        if person is None or person.group_id != bill.group_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="person_id must belong to this bill's group.",
            )

    record_payer_change(db, bill.group_id, bill.payer_person_id, body.person_id)
    bill.payer_person_id = body.person_id
    db.commit()
    db.refresh(bill)
    return _bill_out(bill)


@router.get("/bills/{bill_id}/splits", response_model=list[PersonSplitOut])
def get_bill_splits(bill: Bill = Depends(get_accessible_bill), db: Session = Depends(get_db)):
    """Live per-person breakdown (design.md SS9/SS10) across the bill's
    current participants. Not persisted - see /settlement for that."""
    return compute_bill_splits(bill, bill_participant_people(db, bill))


@router.get("/bills/{bill_id}/settlement", response_model=list[SplitOut])
def get_bill_settlement(bill: Bill = Depends(get_accessible_bill), db: Session = Depends(get_db)):
    """The persisted, payer-trackable settlement view (design.md SS12). Only
    meaningful once a bill is open or closed - 409 before that."""
    try:
        rows = ensure_settlement_rows(db, bill)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    return [split_out_from_model(row) for row in rows]


@router.put("/bills/{bill_id}/settlement/{person_id}/paid", response_model=SplitOut)
def set_split_paid(
    person_id: uuid.UUID,
    body: SetSplitPaid,
    bill: Bill = Depends(get_accessible_bill),
    db: Session = Depends(get_db),
):
    """The payer-controlled "marked as paid" toggle (design.md SS12).
    Enforced: only an open bill's settlement can move, and the payer can't
    be marked paid against themselves."""
    if bill.status != BillStatus.OPEN:
        detail = (
            "Bill is closed and immutable."
            if bill.status == BillStatus.CLOSED
            else "Settlement isn't available until the bill is open."
        )
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)
    if person_id == bill.payer_person_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="The payer isn't marked paid against themselves.",
        )

    sync_bill_splits(db, bill)
    split = get_split_for_person(db, bill.id, person_id)
    if split is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No settlement row for this person on this bill.",
        )

    split.is_paid = body.is_paid
    split.paid_at = datetime.now(timezone.utc) if body.is_paid else None
    db.commit()
    db.refresh(split)
    return split_out_from_model(split)


@router.post("/bills/{bill_id}/close", response_model=BillOut)
def close_bill(bill: Bill = Depends(get_accessible_bill), db: Session = Depends(get_db)):
    """design.md SS12's hard gate: a bill only moves to closed once a payer
    is recorded and every non-payer participant's Split.is_paid is true.
    Closing then freezes the bill - every mutating endpoint refuses a
    closed bill."""
    if bill.status != BillStatus.OPEN:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Only an open bill can be closed."
        )
    if bill.payer_person_id is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Set a payer before closing - settlement has no one to pay back otherwise.",
        )

    rows = sync_bill_splits(db, bill)
    unpaid = [row for row in rows if row.person_id != bill.payer_person_id and not row.is_paid]
    if unpaid:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"{len(unpaid)} person(s) still haven't been marked as paid.",
        )

    bill.status = BillStatus.CLOSED
    bill.closed_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(bill)
    return _bill_out(bill)
