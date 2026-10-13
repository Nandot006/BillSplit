"""Backend Block 12: persisted settlement (design.md SS12).

sync_bill_splits is the only writer of Split rows - it snapshots
app/services/splits.compute_bill_splits' live math into the splits table,
upserting one row per Person currently in the bill's group and carrying
forward any existing is_paid/paid_at rather than resetting it. Called
every time a settlement-facing route touches an OPEN bill (see
ensure_settlement_rows below), so persisted amounts never go stale while
the bill is still editable (CLAUDE.md SS8: assignments stay editable
until the bill is finalized) - closing is the only point they freeze.

ensure_settlement_rows is what routes/bill.py's settlement endpoints call
first: it re-syncs an OPEN bill (so the numbers reflect whatever was just
edited) and simply reads back the frozen rows for a CLOSED one (design.md
SS12: a closed bill is fully immutable, so its Split rows must not be
recomputed even if e.g. a person's display_name later changes).
"""

import uuid

from sqlalchemy.orm import Session

from app.models.bill import Bill, BillStatus
from app.models.person import Person
from app.models.split import Split
from app.services.splits import compute_bill_splits


def sync_bill_splits(db: Session, bill: Bill) -> list[Split]:
    people = (
        db.query(Person)
        .filter(Person.group_id == bill.group_id)
        .order_by(Person.display_name)
        .all()
    )
    live_splits = {s.person_id: s for s in compute_bill_splits(bill, people)}

    existing_rows = {
        row.person_id: row for row in db.query(Split).filter(Split.bill_id == bill.id).all()
    }

    synced: list[Split] = []
    for person_id, live in live_splits.items():
        row = existing_rows.get(person_id)
        if row is None:
            row = Split(bill_id=bill.id, person_id=person_id, is_paid=False, paid_at=None)
            db.add(row)
        row.item_subtotal_share = live.item_subtotal_share
        row.tax_share = live.tax_share
        row.tip_share = live.tip_share
        row.total_owed = live.total_owed
        synced.append(row)

    # A Person no longer part of the live split (e.g. removed from the
    # group since the last sync) shouldn't keep a stale settlement row
    # around - drop it, same as compute_bill_splits already drops them
    # from the live view.
    stale_person_ids = set(existing_rows) - set(live_splits)
    for person_id in stale_person_ids:
        db.delete(existing_rows[person_id])

    db.flush()
    return synced


def ensure_settlement_rows(db: Session, bill: Bill) -> list[Split]:
    """The read path every settlement route uses: OPEN bills get a fresh
    sync (and the sync is committed, since a GET shouldn't leave dangling
    uncommitted writes), CLOSED bills just read back what's already there.
    Raises ValueError for any other status - callers translate that into
    the 409 design.md SS12 implies ("settlement isn't a thing yet")."""
    if bill.status == BillStatus.OPEN:
        rows = sync_bill_splits(db, bill)
        db.commit()
        for row in rows:
            db.refresh(row)
        return rows
    if bill.status == BillStatus.CLOSED:
        return db.query(Split).filter(Split.bill_id == bill.id).all()
    raise ValueError("Bill has no settlement yet - it must be open or closed first.")


def get_split_for_person(db: Session, bill_id: uuid.UUID, person_id: uuid.UUID) -> Split | None:
    return db.query(Split).filter(Split.bill_id == bill_id, Split.person_id == person_id).first()
