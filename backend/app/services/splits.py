"""Live per-person bill-split calculation (design.md SS9/SS10, Backend
Block 10). Deliberately not persisted anywhere yet - the Split entity
design.md SS5 describes (with is_paid/paid_at for settlement tracking) is
Block 12's job. Keeping the money math here, computed fresh from the
bill's current items/assignments and the group's current people, means:

  1. Block 10 has something concrete and testable to show for "tax
     recalculation" even though there's no Split table yet to write into.
  2. It's automatically correct after a person is removed
     (services/prediction/pipeline.redistribute_bill_after_person_removal
     already re-scored/re-normalized the assignments; this module just
     reads whatever they currently are) - no separate recalculation step.
  3. Block 12 can build its persisted Split rows directly from
     compute_bill_splits' output instead of re-deriving the rounding rules.
"""

import uuid
from dataclasses import dataclass
from decimal import ROUND_DOWN, Decimal

from app.models.bill import Bill
from app.models.person import Person

CENT = Decimal("0.01")


@dataclass
class PersonSplit:
    person_id: uuid.UUID
    display_name: str
    item_subtotal_share: Decimal
    tax_share: Decimal
    tip_share: Decimal
    total_owed: Decimal


def _split_evenly(total: Decimal, shares: list[tuple[uuid.UUID, str]]) -> dict[uuid.UUID, Decimal]:
    """design.md SS10's largest-remainder rounding, specialized for an
    *even* split (which is every case this app has - tax, tip, and a shared
    item's cost per design.md SS7 are all split evenly, never
    proportionally): floor everyone's equal share to the cent, then hand
    the leftover pennies out one at a time so the shares always sum to
    exactly `total` (no off-by-cent bugs, per CLAUDE.md SS9). Because every
    share starts out identical, "largest remainder" ties across the board -
    so who gets a leftover penny is decided purely by the tie-break: each
    id's paired key (a Person's display_name for tax/tip, per design.md
    SS11's tie-break style) and then the id itself, for a fully
    deterministic result.
    """
    if not shares:
        return {}

    n = len(shares)
    total_cents = int((total * 100).to_integral_value(rounding=ROUND_DOWN))
    base_cents, remainder_cents = divmod(total_cents, n)

    result = {item_id: (Decimal(base_cents) / 100).quantize(CENT) for item_id, _ in shares}
    ordered = sorted(shares, key=lambda s: (s[1], str(s[0])))
    for item_id, _ in ordered[:remainder_cents]:
        result[item_id] += CENT
    return result


def compute_bill_splits(bill: Bill, people: list[Person]) -> list[PersonSplit]:
    """The full per-person breakdown for `bill`, computed against whichever
    `people` are passed in - always the group's *current* Person list, so
    the caller (routes/bill.py's GET .../splits) controls "current" simply
    by querying People fresh; a person removed from the group is excluded
    just by not being in that list, no special-casing needed here."""
    if not people:
        return []

    tiebreak_key = {p.id: p.display_name for p in people}
    item_totals: dict[uuid.UUID, Decimal] = {p.id: Decimal("0.00") for p in people}

    for item in bill.items:
        current_assignees = [a for a in item.assignments if a.person_id in tiebreak_key]
        if not current_assignees:
            continue
        item_total = (item.price * item.quantity).quantize(CENT, rounding=ROUND_DOWN)
        shares = _split_evenly(
            item_total,
            [(a.person_id, tiebreak_key[a.person_id]) for a in current_assignees],
        )
        for person_id, amount in shares.items():
            item_totals[person_id] += amount

    people_shares = [(p.id, p.display_name) for p in people]
    tax_shares = _split_evenly(bill.tax_total or Decimal("0"), people_shares)
    tip_shares = _split_evenly(bill.tip_total, people_shares)

    return [
        PersonSplit(
            person_id=p.id,
            display_name=p.display_name,
            item_subtotal_share=item_totals[p.id],
            tax_share=tax_shares[p.id],
            tip_share=tip_shares[p.id],
            total_owed=item_totals[p.id] + tax_shares[p.id] + tip_shares[p.id],
        )
        for p in people
    ]
