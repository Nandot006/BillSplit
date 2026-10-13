"""Backend Block 11: payer tracking + prefill/tie-break (design.md SS11).

`record_payer_change` is the only writer of PayerHistory rows - called by
routes/bill.py's set_bill_payer whenever a Bill's payer_person_id is set or
changed, never on plain bill reads. `suggest_payer` is a pure read: it
never mutates PayerHistory, so calling it repeatedly (e.g. every time a
client loads the payer dropdown) is always safe.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.payer_history import PayerHistory
from app.models.person import Person

# Smaller than any real timestamp, so a Person with no PayerHistory row
# (never paid) naturally sorts first in suggest_payer's ascending sort -
# exactly design.md SS11's "NULL (never paid) sorted first" rule, without
# needing a separate has-paid flag in the sort key.
_NEVER_PAID = datetime.min.replace(tzinfo=timezone.utc)


def record_payer_change(
    db: Session,
    group_id: uuid.UUID,
    old_payer_id: uuid.UUID | None,
    new_payer_id: uuid.UUID | None,
) -> None:
    """Moves one "payment" credit from `old_payer_id` to `new_payer_id`
    within `group_id`'s history. A no-op if the payer didn't actually
    change (idempotent re-PUT of the same payer), so callers can call this
    unconditionally after every set_bill_payer request."""
    if old_payer_id == new_payer_id:
        return

    if old_payer_id is not None:
        old_row = db.get(PayerHistory, (group_id, old_payer_id))
        if old_row is not None and old_row.payment_count > 0:
            old_row.payment_count -= 1

    if new_payer_id is not None:
        new_row = db.get(PayerHistory, (group_id, new_payer_id))
        if new_row is None:
            new_row = PayerHistory(group_id=group_id, person_id=new_payer_id, payment_count=0)
            db.add(new_row)
        new_row.payment_count += 1
        new_row.last_paid_at = datetime.now(timezone.utc)


def suggest_payer(db: Session, group_id: uuid.UUID) -> Person | None:
    """design.md SS11's prefill: whoever paid least recently, NULL
    (never paid) first, tie-broken alphabetically by display_name. Returns
    None only if the group has no people at all. Always overridable by the
    caller - this is a suggestion, not something enforced."""
    people = db.query(Person).filter(Person.group_id == group_id).all()
    if not people:
        return None

    histories = {
        h.person_id: h
        for h in db.query(PayerHistory).filter(PayerHistory.group_id == group_id).all()
    }

    def sort_key(person: Person) -> tuple[datetime, str]:
        history = histories.get(person.id)
        last_paid_at = history.last_paid_at if history is not None else None
        if last_paid_at is None:
            last_paid_at = _NEVER_PAID
        elif last_paid_at.tzinfo is None:
            # SQLite (used in tests) hands back naive datetimes for a
            # DateTime(timezone=True) column even though it was written
            # tz-aware; Postgres (production) never does this. Assume UTC
            # rather than let the comparison below blow up.
            last_paid_at = last_paid_at.replace(tzinfo=timezone.utc)
        return (last_paid_at, person.display_name)

    return min(people, key=sort_key)
