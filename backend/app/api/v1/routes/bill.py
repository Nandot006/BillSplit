import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_accessible_bill, get_accessible_group, get_db
from app.models.bill import Bill, BillStatus
from app.models.bill_item import BillItem
from app.models.bill_item_tags import BillItemDietaryFlag, BillItemFlavorTag
from app.models.group import Group
from app.models.person import Person
from app.schemas.bill import BillCreate, BillDetailOut, BillOut, BillUpdate
from app.schemas.bill_item import (
    AssignItemRequest,
    BillItemCreate,
    BillItemOut,
    bill_item_out_from_model,
)
from app.schemas.payer import SetBillPayer
from app.schemas.split import PersonSplitOut, SetSplitPaid, SplitOut, split_out_from_model
from app.services.bills import recompute_bill_totals
from app.services.ocr.pipeline import run_bill_processing_job
from app.services.payer import record_payer_change
from app.services.prediction.pipeline import generate_predictions_for_bill, record_correction
from app.services.settlement import ensure_settlement_rows, get_split_for_person, sync_bill_splits
from app.services.splits import compute_bill_splits

router = APIRouter()


@router.post(
    "/groups/{group_id}/bills", response_model=BillOut, status_code=status.HTTP_201_CREATED
)
def create_bill(
    body: BillCreate,
    background_tasks: BackgroundTasks,
    group: Group = Depends(get_accessible_group),
    db: Session = Depends(get_db),
):
    """Any group member can start a bill (unlike group membership, which is
    creator-only - see get_accessible_group vs require_group_creator).
    image_storage_path present -> PROCESSING, and the OCR -> taxonomy ->
    prediction pipeline (Backend Blocks 8-9) is queued as a background task
    so this request doesn't block on it (design.md SS8); absent ->
    NEEDS_MANUAL_ENTRY."""
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
    db.commit()
    db.refresh(bill)

    if bill.status == BillStatus.PROCESSING:
        background_tasks.add_task(run_bill_processing_job, bill.id)

    return bill


@router.get("/groups/{group_id}/bills", response_model=list[BillOut])
def list_group_bills(group: Group = Depends(get_accessible_group), db: Session = Depends(get_db)):
    return db.query(Bill).filter(Bill.group_id == group.id).order_by(Bill.created_at.desc()).all()


@router.get("/bills/{bill_id}", response_model=BillDetailOut)
def get_bill(bill: Bill = Depends(get_accessible_bill)):
    return BillDetailOut(
        **BillOut.model_validate(bill).model_dump(),
        items=[bill_item_out_from_model(item) for item in bill.items],
    )


@router.patch("/bills/{bill_id}", response_model=BillOut)
def update_bill(
    body: BillUpdate,
    bill: Bill = Depends(get_accessible_bill),
    db: Session = Depends(get_db),
):
    if bill.status == BillStatus.CLOSED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Bill is closed and immutable."
        )
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(bill, field, value)
    recompute_bill_totals(bill)
    db.commit()
    db.refresh(bill)
    return bill


@router.post(
    "/bills/{bill_id}/items", response_model=BillItemOut, status_code=status.HTTP_201_CREATED
)
def add_bill_item(
    body: BillItemCreate,
    bill: Bill = Depends(get_accessible_bill),
    db: Session = Depends(get_db),
):
    """Manual item entry - the OCR-failure fallback buildguide.md Block 7
    calls for, and (for bills that skip OCR entirely) the normal way a
    needs_manual_entry bill gets its items."""
    if bill.status != BillStatus.NEEDS_MANUAL_ENTRY:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Items can only be added by hand while the bill is in needs_manual_entry.",
        )
    item = BillItem(
        bill_id=bill.id,
        parsed_name=body.parsed_name,
        price=body.price,
        quantity=body.quantity,
        base_type=body.base_type,
    )
    db.add(item)
    db.flush()
    for tag in body.flavor_tags:
        db.add(BillItemFlavorTag(bill_item_id=item.id, flavor_tag=tag))
    for flag in body.dietary_flags:
        db.add(BillItemDietaryFlag(bill_item_id=item.id, dietary_flag=flag))
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
    if bill.status != BillStatus.NEEDS_MANUAL_ENTRY:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Items can only be removed while the bill is in needs_manual_entry.",
        )
    item = db.get(BillItem, item_id)
    if item is None or item.bill_id != bill.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Item not found on this bill."
        )
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
    running the Block 9 scorer over its items first (a manually-entered
    item can carry base_type/flavor/dietary tags just like an OCR'd one -
    see BillItemCreate - so there's genuinely something to predict from
    whenever the user tagged their items on the way in). Items left
    untagged simply get no prediction and wait for a manual assignment via
    PUT .../items/{item_id}/assign, same as any needs_review bill."""
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
    return bill


@router.put("/bills/{bill_id}/items/{item_id}/assign", response_model=BillItemOut)
def assign_bill_item(
    item_id: uuid.UUID,
    body: AssignItemRequest,
    bill: Bill = Depends(get_accessible_bill),
    db: Session = Depends(get_db),
):
    """The confirm/correct action (PRD SS5 step 4, design.md SS8): sets an
    item's sole assignee, capturing a learned_correction signal whenever
    this actually changes who the item is assigned to (record_correction is
    a no-op if corrected_person_id is already the item's only assignee).
    Available for the whole review/edit window - needs_review (still being
    reviewed) and open (already confirmed, but "editable until finalized"
    per CLAUDE.md SS8) - never once the bill is closed."""
    if bill.status not in (BillStatus.NEEDS_REVIEW, BillStatus.OPEN):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Items can only be (re)assigned while the bill is in needs_review or open.",
        )
    item = db.get(BillItem, item_id)
    if item is None or item.bill_id != bill.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Item not found on this bill."
        )

    person = db.get(Person, body.person_id)
    if person is None or person.group_id != bill.group_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="person_id must belong to this bill's group.",
        )

    record_correction(db, item, body.person_id)
    # Backend Block 12: an assignment change after the bill is open shifts
    # who owes what (item_subtotal_share), so keep the persisted Split
    # rows current rather than letting them drift until the next explicit
    # settlement read (design.md SS12 / CLAUDE.md SS8 - items stay
    # editable up to closing, and the settlement view has to reflect that).
    # Before OPEN, no Split rows exist yet (they're created at confirm_bill
    # per Block 12 above), so there's nothing to sync.
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
    one assignment - the point where PRD SS5 step 4's "user reviews and
    corrects" is done and the bill is ready for settlement work (Blocks
    11-12). Doesn't require every prediction to have been reviewed
    individually, only that nothing is left completely unassigned (design.md
    SS6's hard-restriction edge case is exactly the case this guards
    against - a human must have picked someone for those items by hand)."""
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
    # Backend Block 12: this is the first point Split rows exist for this
    # bill (design.md SS12) - everything before here was Block 10's live,
    # unpersisted view. sync_bill_splits creates one row per current group
    # member with is_paid defaulted false.
    sync_bill_splits(db, bill)
    db.commit()
    db.refresh(bill)
    return bill


@router.put("/bills/{bill_id}/payer", response_model=BillOut)
def set_bill_payer(
    body: SetBillPayer,
    bill: Bill = Depends(get_accessible_bill),
    db: Session = Depends(get_db),
):
    """buildguide.md Backend Block 11: sets (or clears, with person_id =
    None) who fronted the money for this bill. Recorded into PayerHistory
    (app/services/payer.record_payer_change) so a future bill's payer
    dropdown can prefill to whoever paid least recently (design.md SS11).
    Stays a plain, always-overridable PUT rather than something gated
    behind bill status the way item edits are - with one exception: a
    closed bill's payer is settled history and must not move (CLAUDE.md
    SS9 / design.md SS12)."""
    if bill.status == BillStatus.CLOSED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Bill is closed and immutable."
        )
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
    return bill


@router.get("/bills/{bill_id}/splits", response_model=list[PersonSplitOut])
def get_bill_splits(bill: Bill = Depends(get_accessible_bill), db: Session = Depends(get_db)):
    """Live per-person breakdown (design.md SS9/SS10) - Backend Block 10.
    Not persisted: the Split entity with is_paid/paid_at (design.md SS5) is
    Block 12's settlement work. Always reflects the bill's current
    items/assignments against the group's current People, so a person
    removed from the group (see routes/group.py's remove_person_from_group,
    which redistributes their assignments first via
    services/prediction/pipeline.redistribute_bill_after_person_removal) is
    simply absent here with no extra step."""
    people = (
        db.query(Person)
        .filter(Person.group_id == bill.group_id)
        .order_by(Person.display_name)
        .all()
    )
    return compute_bill_splits(bill, people)


@router.get("/bills/{bill_id}/settlement", response_model=list[SplitOut])
def get_bill_settlement(bill: Bill = Depends(get_accessible_bill), db: Session = Depends(get_db)):
    """Backend Block 12 (design.md SS12): the persisted, payer-trackable
    settlement view - each Person's total_owed alongside is_paid/paid_at.
    Distinct from GET .../splits above (Block 10's live, unpersisted
    amounts, still useful for previewing a split before the bill is even
    open). Only meaningful once a bill has reached open (or closed) -
    409 before that, since there's no settlement to show yet."""
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
    """The payer-controlled "marked as paid" toggle (design.md SS12). This
    app has no per-request notion of "which Person is making this call" -
    a User can be a group's creator managing shadow contacts rather than a
    specific Person themselves - so, like set_bill_payer's own
    always-overridable design, "payer-controlled" is a product/UI
    convention (the payer is who's expected to use this) rather than a
    hard identity check enforced here. What *is* enforced: only an open
    bill's settlement can move (closed is frozen history, design.md SS12),
    and the payer can't mark their own row paid - they fronted the money,
    they don't owe it to themselves."""
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
    has been recorded *and* every non-payer Person's Split.is_paid is true
    - settlement means "everyone paid the payer back," which has no
    meaning with nobody recorded as having fronted the money, so a missing
    payer is stopped here explicitly rather than vacuously passing the
    is_paid check. Re-syncs Split rows first so the gate is checked
    against current amounts/membership, not a possibly-stale snapshot.
    Closing then freezes the bill: every other mutating endpoint above
    already checks for BillStatus.CLOSED and refuses (update_bill,
    add/delete item, assign_bill_item, set_bill_payer, set_split_paid) -
    this is simply where that status gets set. Closed bills still feed the
    taxonomy-vector learning signal (design.md SS8/SS12) - nothing here
    touches PersonTaxonomyScore, so that stays intact."""
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
    return bill
