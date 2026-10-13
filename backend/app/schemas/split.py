import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class PersonSplitOut(BaseModel):
    """Backend Block 10 - the live (unpersisted) per-person breakdown from
    app/services/splits.compute_bill_splits. from_attributes lets this
    validate straight off that module's PersonSplit dataclass instances."""

    model_config = ConfigDict(from_attributes=True)

    person_id: uuid.UUID
    display_name: str
    item_subtotal_share: Decimal
    tax_share: Decimal
    tip_share: Decimal
    total_owed: Decimal


class SplitOut(BaseModel):
    """Backend Block 12 - the persisted settlement record (design.md SS5/
    SS12), built from a Split ORM instance via split_out_from_model. Unlike
    PersonSplitOut above (Block 10's live, unpersisted view), this carries
    is_paid/paid_at, which only exist once a bill has reached Block 12's
    settlement stage."""

    id: uuid.UUID
    bill_id: uuid.UUID
    person_id: uuid.UUID
    display_name: str
    item_subtotal_share: Decimal
    tax_share: Decimal
    tip_share: Decimal
    total_owed: Decimal
    is_paid: bool
    paid_at: datetime | None = None


class SetSplitPaid(BaseModel):
    """Body for the payer-controlled "mark as paid" action (design.md
    SS12). is_paid lets the payer un-mark a mistaken tap, not just mark -
    design.md doesn't forbid correcting that before the bill closes."""

    is_paid: bool


def split_out_from_model(split) -> SplitOut:
    """Builds a SplitOut from a Split ORM instance - written as a plain
    function (mirroring schemas/bill_item.bill_item_out_from_model) rather
    than relying on from_attributes, because display_name lives on the
    related Person, not on Split itself."""
    return SplitOut(
        id=split.id,
        bill_id=split.bill_id,
        person_id=split.person_id,
        display_name=split.person.display_name,
        item_subtotal_share=split.item_subtotal_share,
        tax_share=split.tax_share,
        tip_share=split.tip_share,
        total_owed=split.total_owed,
        is_paid=split.is_paid,
        paid_at=split.paid_at,
    )
