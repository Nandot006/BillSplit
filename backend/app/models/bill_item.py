import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base
from app.models.taxonomy import BaseType

if TYPE_CHECKING:
    from app.models.bill import Bill
    from app.models.bill_item_assignment import BillItemAssignment
    from app.models.bill_item_tags import BillItemDietaryFlag, BillItemFlavorTag


class BillItem(Base):
    """A line item on a Bill (design.md SS5). raw_ocr_text is null when the
    item was typed in by hand (needs_manual_entry) rather than extracted by
    the OCR pipeline (Backend Block 8). base_type/flavor_tags/dietary_flags
    are populated either by the user (manual entry) or by the OCR->taxonomy
    LLM step (Block 8) - the schema doesn't care which."""

    __tablename__ = "bill_items"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    bill_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("bills.id", ondelete="CASCADE"), nullable=False
    )
    raw_ocr_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    parsed_name: Mapped[str] = mapped_column(String, nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    base_type: Mapped[BaseType | None] = mapped_column(
        SAEnum(BaseType, name="base_type", native_enum=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    bill: Mapped["Bill"] = relationship(back_populates="items")
    flavor_tags: Mapped[list["BillItemFlavorTag"]] = relationship(
        back_populates="bill_item", cascade="all, delete-orphan"
    )
    dietary_flags: Mapped[list["BillItemDietaryFlag"]] = relationship(
        back_populates="bill_item", cascade="all, delete-orphan"
    )
    assignments: Mapped[list["BillItemAssignment"]] = relationship(
        back_populates="bill_item", cascade="all, delete-orphan"
    )
