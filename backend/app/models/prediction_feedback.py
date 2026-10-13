import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.bill_item import BillItem
    from app.models.person import Person


class PredictionFeedback(Base):
    """A record of one correction to a predicted item->person assignment
    (design.md SS5/SS8) - the training/learning signal for
    PersonTaxonomyScore updates (app/services/prediction/pipeline.py's
    apply_learned_correction). original_predicted_person_id is NULL when
    there was nothing to correct against yet (e.g. a hard restriction
    excluded every candidate and a human picked one from scratch) - the
    corrected_person still gets a positive learning signal in that case,
    there just isn't a "wrong guess" to also push away from.

    original_predicted_person_id uses ondelete=SET NULL rather than CASCADE:
    if that Person row is later removed from the group (Block 5's hard
    delete), we'd rather keep this feedback row with an unknown original
    than lose the record of the correction entirely. corrected_person_id
    stays required (never NULL) and cascades with its Person, matching the
    rest of this schema's delete style - a future block revisiting person
    hard-delete (already flagged in app/models/person.py's history) can
    reconsider this if it turns out to matter for the learning signal.
    """

    __tablename__ = "prediction_feedback"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    bill_item_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("bill_items.id", ondelete="CASCADE"), nullable=False
    )
    original_predicted_person_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("people.id", ondelete="SET NULL"), nullable=True
    )
    corrected_person_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("people.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    bill_item: Mapped["BillItem"] = relationship()
    original_predicted_person: Mapped["Person | None"] = relationship(
        foreign_keys=[original_predicted_person_id]
    )
    corrected_person: Mapped["Person"] = relationship(foreign_keys=[corrected_person_id])
