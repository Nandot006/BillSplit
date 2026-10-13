import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Numeric, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.bill import Bill
    from app.models.person import Person


class Split(Base):
    """The persisted per-person settlement record for a Bill (design.md SS5/
    SS12, buildguide.md Backend Block 12). Amounts mirror
    app/services/splits.compute_bill_splits' live math (Block 10) - same
    rounding rules, just snapshotted into a row so is_paid/paid_at have
    somewhere to live. app/services/settlement.sync_bill_splits is the only
    writer: it upserts one row per Person currently in the bill's group,
    recomputing amounts from compute_bill_splits every time it's called (so
    a Split row's money fields never drift from the bill's current items/
    assignments right up until the bill closes), while carrying forward any
    existing is_paid/paid_at instead of resetting it on every sync.

    A Split row exists for every Person, including the bill's payer - their
    own row is simply excluded from the close-gate check (design.md SS12:
    "every *non-payer* Person's Split.is_paid"), since they fronted the
    money rather than owing it to themselves.
    """

    __tablename__ = "splits"
    __table_args__ = (UniqueConstraint("bill_id", "person_id"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    bill_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("bills.id", ondelete="CASCADE"), nullable=False
    )
    person_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("people.id", ondelete="CASCADE"), nullable=False
    )
    item_subtotal_share: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    tax_share: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    tip_share: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    total_owed: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    is_paid: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    bill: Mapped["Bill"] = relationship()
    person: Mapped["Person"] = relationship()
