import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class SetBillPayer(BaseModel):
    # None clears the payer (e.g. the bill's payer decision hasn't been
    # made yet, or is being unset before choosing someone else).
    person_id: uuid.UUID | None = None


class PayerSuggestionOut(BaseModel):
    """Backend Block 11 - app/services/payer.suggest_payer's result, for a
    client's payer dropdown to prefill against (design.md SS11). Always
    manually overridable: this is a default, not a constraint on
    set_bill_payer."""

    model_config = ConfigDict(from_attributes=True)

    person_id: uuid.UUID
    display_name: str
    payment_count: int
    last_paid_at: datetime | None = None
