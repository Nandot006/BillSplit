import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.bill import Bill
    from app.models.person import Person


class BillParticipant(Base):
    """Who was actually on a given bill (decision 2026-11-20). A group is
    "people who split bills together"; a bill's participants are the subset
    of that group who were at this particular meal.

    Participants - not the whole group - are who:
      - the scorer predicts items for (design.md SS6),
      - tax and tip are split evenly across (design.md SS10),
      - get a settlement row (design.md SS12),
      - can be removed from just this bill, with their items re-scored
        against the remaining participants (design.md SS9).

    Composite primary key, same style as the item tag join tables.
    """

    __tablename__ = "bill_participants"

    bill_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("bills.id", ondelete="CASCADE"), primary_key=True
    )
    person_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("people.id", ondelete="CASCADE"), primary_key=True
    )

    bill: Mapped["Bill"] = relationship(back_populates="participants")
    person: Mapped["Person"] = relationship()
