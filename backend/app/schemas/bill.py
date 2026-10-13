import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.models.bill import BillStatus
from app.schemas.bill_item import BillItemOut


class BillCreate(BaseModel):
    # Web/Mobile upload the image straight to Supabase Storage with their
    # own Supabase client, then pass us the resulting path - our backend
    # never receives the raw image bytes directly (Backend Block 8 will
    # fetch it from Storage when it wires up the OCR provider).
    image_storage_path: str | None = None
    merchant_name: str | None = None
    bill_date: date | None = None


class BillUpdate(BaseModel):
    merchant_name: str | None = None
    bill_date: date | None = None
    tax_total: Decimal | None = Field(default=None, ge=0)
    tip_total: Decimal | None = Field(default=None, ge=0)


class BillOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    group_id: uuid.UUID
    image_storage_path: str | None = None
    merchant_name: str | None = None
    bill_date: date | None = None
    subtotal: Decimal | None = None
    tax_total: Decimal | None = None
    tip_total: Decimal
    grand_total: Decimal | None = None
    status: BillStatus
    payer_person_id: uuid.UUID | None = None
    created_at: datetime
    closed_at: datetime | None = None


class BillDetailOut(BillOut):
    items: list[BillItemOut] = []
