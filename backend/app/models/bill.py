import enum
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Date, DateTime, ForeignKey, Numeric, String
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.bill_item import BillItem
    from app.models.group import Group
    from app.models.person import Person


class BillStatus(str, enum.Enum):
    UPLOADING = "uploading"
    PROCESSING = "processing"
    NEEDS_MANUAL_ENTRY = "needs_manual_entry"
    NEEDS_REVIEW = "needs_review"
    OPEN = "open"
    CLOSED = "closed"


class Bill(Base):
    """An uploaded receipt (design.md SS5). image_storage_path is a Supabase
    Storage path - Web/Mobile upload the image directly to Supabase Storage
    with their own Supabase client, then create the Bill here with the
    resulting path. subtotal/grand_total are derived from items (see
    app/services/bills.py); tax_total/tip_total are bill-level fields set
    independently, not derived (design.md SS10 - split evenly, not
    proportional to items)."""

    __tablename__ = "bills"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    group_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("groups.id", ondelete="CASCADE"), nullable=False
    )
    image_storage_path: Mapped[str | None] = mapped_column(String, nullable=True)
    merchant_name: Mapped[str | None] = mapped_column(String, nullable=True)
    bill_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    subtotal: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    tax_total: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    tip_total: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, default=Decimal("0"))
    grand_total: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    status: Mapped[BillStatus] = mapped_column(
        SAEnum(BillStatus, name="bill_status", native_enum=True), nullable=False
    )
    payer_person_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("people.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    group: Mapped["Group"] = relationship(back_populates="bills")
    items: Mapped[list["BillItem"]] = relationship(
        back_populates="bill", cascade="all, delete-orphan"
    )
    payer: Mapped[Optional["Person"]] = relationship(foreign_keys=[payer_person_id])
