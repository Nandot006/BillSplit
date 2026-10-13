import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.taxonomy import DietaryFlag, FlavorTag

if TYPE_CHECKING:
    from app.models.bill_item import BillItem


class BillItemFlavorTag(Base):
    """Join table: a BillItem can carry several flavor tags (design.md SS5).
    Composite primary key, matching design.md's schema exactly - no
    surrogate id needed since (bill_item_id, flavor_tag) is already unique
    and meaningful."""

    __tablename__ = "bill_item_flavor_tags"

    bill_item_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("bill_items.id", ondelete="CASCADE"), primary_key=True
    )
    flavor_tag: Mapped[FlavorTag] = mapped_column(
        SAEnum(FlavorTag, name="flavor_tag", native_enum=True), primary_key=True
    )

    bill_item: Mapped["BillItem"] = relationship(back_populates="flavor_tags")


class BillItemDietaryFlag(Base):
    """Join table: a BillItem can carry several dietary flags (design.md SS5)."""

    __tablename__ = "bill_item_dietary_flags"

    bill_item_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("bill_items.id", ondelete="CASCADE"), primary_key=True
    )
    dietary_flag: Mapped[DietaryFlag] = mapped_column(
        SAEnum(DietaryFlag, name="dietary_flag", native_enum=True), primary_key=True
    )

    bill_item: Mapped["BillItem"] = relationship(back_populates="dietary_flags")
