import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.group import Group
    from app.models.person import Person


class PayerHistory(Base):
    """design.md SS11 / buildguide.md Backend Block 11: a lightweight per-
    (group, person) counter of how many times that person has been a
    bill's payer, and when they most recently paid - the data the payer
    prefill/tie-break (app/services/payer.suggest_payer) reads to default
    the payer dropdown to whoever paid least recently (design.md SS11: sort
    by last_paid_at ascending, NULL/never-paid first, then alphabetically
    by display_name).

    One row per Person who has ever been recorded as a bill's payer in
    this group - a Person with no row here has never paid (treated as
    NULL last_paid_at, which sorts first). Rows are written/updated by
    app/services/payer.record_payer_change whenever a Bill's
    payer_person_id is set or changed (routes/bill.py's set_bill_payer),
    not derived from Bill rows directly, so "who paid most recently" stays
    a single fast lookup instead of a scan over bill history.
    """

    __tablename__ = "payer_history"

    group_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("groups.id", ondelete="CASCADE"), primary_key=True
    )
    person_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("people.id", ondelete="CASCADE"), primary_key=True
    )
    payment_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    group: Mapped["Group"] = relationship()
    person: Mapped["Person"] = relationship()
