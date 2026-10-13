import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Float, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.bill_item import BillItem
    from app.models.person import Person


class BillItemAssignment(Base):
    """Many-to-many BillItem <-> Person (design.md SS5/SS7) - a BillItem can
    be assigned to more than one Person to support shared items. is_predicted
    distinguishes a scorer-produced row (Backend Block 9) from one a human
    added/edited by hand; confidence_score is only meaningful when
    is_predicted is True (design.md SS6/SS8).

    share_fraction is stored as a plain float rather than Numeric - unlike
    the money columns on Bill/Split, this is a weight (1 / assigned_count)
    consumed by the settlement math in Block 12, not currency itself, so it
    doesn't need cent-precision guarantees.

    UniqueConstraint prevents the same Person being assigned to the same
    item twice (the "add a person to a shared item" endpoint should no-op
    or reject a duplicate rather than create a second row).
    """

    __tablename__ = "bill_item_assignments"
    __table_args__ = (UniqueConstraint("bill_item_id", "person_id"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    bill_item_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("bill_items.id", ondelete="CASCADE"), nullable=False
    )
    person_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("people.id", ondelete="CASCADE"), nullable=False
    )
    is_predicted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    confidence_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    share_fraction: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)

    bill_item: Mapped["BillItem"] = relationship(back_populates="assignments")
    person: Mapped["Person"] = relationship()
