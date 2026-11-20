// Pure helpers for the bill screens - kept out of components so the rules
// they encode (design.md §6, §12) are unit-tested on their own.

import type { BillDetail, BillItem, BillStatus, SettlementRow } from "@billsplit/shared-types";

import { toCents } from "./money";

export const STATUS_LABELS: Record<BillStatus, string> = {
  uploading: "Uploading",
  processing: "Reading receipt",
  needs_manual_entry: "Needs items",
  needs_review: "Check who had what",
  open: "Settling up",
  closed: "Settled",
};

/** design.md §6: a guess under 40% confidence gets flagged for a look. */
export const LOW_CONFIDENCE = 0.4;

export type AssignmentState = "unassigned" | "guess-check" | "guess" | "confirmed" | "shared";

export function itemAssignmentState(item: BillItem): AssignmentState {
  const a = item.assignments;
  if (a.length === 0) return "unassigned";
  if (a.length > 1) return "shared";
  if (!a[0].is_predicted) return "confirmed";
  return (a[0].confidence_score ?? 0) < LOW_CONFIDENCE ? "guess-check" : "guess";
}

export function lineTotalCents(item: BillItem): number {
  return toCents(item.price) * item.quantity;
}

export interface ReviewSummary {
  unassigned: number;
  toCheck: number;
}

export function reviewSummary(bill: BillDetail): ReviewSummary {
  let unassigned = 0;
  let toCheck = 0;
  for (const item of bill.items) {
    const state = itemAssignmentState(item);
    if (state === "unassigned") unassigned++;
    if (state === "guess-check") toCheck++;
  }
  return { unassigned, toCheck };
}

export interface CloseReadiness {
  canClose: boolean;
  /** Why not, in words for the person looking at the button. */
  reason: string | null;
  unpaidNames: string[];
}

/** design.md §12: closing needs a payer and every non-payer marked paid. */
export function closeReadiness(
  payerPersonId: string | null,
  settlement: SettlementRow[],
): CloseReadiness {
  if (!payerPersonId) {
    return { canClose: false, reason: "Choose who paid first.", unpaidNames: [] };
  }
  const unpaid = settlement.filter((row) => row.person_id !== payerPersonId && !row.is_paid);
  if (unpaid.length > 0) {
    const names = unpaid.map((row) => row.display_name);
    return {
      canClose: false,
      reason: `Waiting on ${names.length === 1 ? names[0] : `${names.length} people`} to pay back.`,
      unpaidNames: names,
    };
  }
  return { canClose: true, reason: null, unpaidNames: [] };
}

/** Total still owed to the payer: everyone else's unpaid rows. */
export function outstandingCents(
  payerPersonId: string | null,
  settlement: SettlementRow[],
): number {
  return settlement
    .filter((row) => row.person_id !== payerPersonId && !row.is_paid)
    .reduce((sum, row) => sum + toCents(row.total_owed), 0);
}
