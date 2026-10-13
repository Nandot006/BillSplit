from decimal import Decimal

from app.models.bill import Bill


def recompute_bill_totals(bill: Bill) -> None:
    """Recomputes subtotal/grand_total from the bill's current items.
    Call this after adding or removing a BillItem. Tax/tip are independent
    bill-level fields (design.md SS10: split evenly across people, not
    proportional to items), so they're never derived here - only read."""
    subtotal = sum((item.price * item.quantity for item in bill.items), Decimal("0"))
    bill.subtotal = subtotal
    bill.grand_total = subtotal + (bill.tax_total or Decimal("0")) + bill.tip_total
