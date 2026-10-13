import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.models.taxonomy import BaseType, DietaryFlag, FlavorTag


class BillItemCreate(BaseModel):
    parsed_name: str = Field(min_length=1, max_length=300)
    price: Decimal = Field(ge=0)
    quantity: int = Field(default=1, ge=1)
    base_type: BaseType | None = None
    flavor_tags: list[FlavorTag] = []
    dietary_flags: list[DietaryFlag] = []


class BillItemAssignmentOut(BaseModel):
    """One Person assigned to a BillItem (design.md SS5/SS7).
    confidence_score is only meaningful when is_predicted is True."""

    id: uuid.UUID
    person_id: uuid.UUID
    is_predicted: bool
    confidence_score: float | None = None
    share_fraction: float


class AssignItemRequest(BaseModel):
    """Body for the single-assignee confirm/correct action (Backend
    Block 9, PRD SS5 step 4)."""

    person_id: uuid.UUID


class BillItemOut(BaseModel):
    id: uuid.UUID
    bill_id: uuid.UUID
    raw_ocr_text: str | None = None
    parsed_name: str
    price: Decimal
    quantity: int
    base_type: BaseType | None = None
    flavor_tags: list[FlavorTag] = []
    dietary_flags: list[DietaryFlag] = []
    assignments: list[BillItemAssignmentOut] = []
    created_at: datetime


def bill_item_out_from_model(item) -> BillItemOut:
    """Builds a BillItemOut from a BillItem ORM instance. Written as a plain
    function rather than relying on Pydantic's from_attributes, because
    flavor_tags/dietary_flags on the model are lists of join-table rows
    (BillItemFlavorTag/BillItemDietaryFlag), not plain enum values."""
    return BillItemOut(
        id=item.id,
        bill_id=item.bill_id,
        raw_ocr_text=item.raw_ocr_text,
        parsed_name=item.parsed_name,
        price=item.price,
        quantity=item.quantity,
        base_type=item.base_type,
        flavor_tags=[t.flavor_tag for t in item.flavor_tags],
        dietary_flags=[d.dietary_flag for d in item.dietary_flags],
        assignments=[
            BillItemAssignmentOut(
                id=a.id,
                person_id=a.person_id,
                is_predicted=a.is_predicted,
                confidence_score=a.confidence_score,
                share_fraction=a.share_fraction,
            )
            for a in item.assignments
        ],
        created_at=item.created_at,
    )
