"use client";

// The itemized breakdown, laid out like the receipt it came from: one line
// per item with its price, and under it who had it. Guesses the scorer
// wasn't sure about are highlighted, like someone went over the receipt
// with a highlighter. What's editable depends on the bill's stage.

import type { BillDetail, BillItem, BillItemCreate, Person } from "@billsplit/shared-types";
import { useState } from "react";

import { Avatar, Button } from "@/components/ui";
import { itemAssignmentState, lineTotalCents } from "@/lib/bill";
import { formatCents, formatMoney } from "@/lib/money";
import { BASE_TYPE_LABELS } from "@/lib/taxonomy";

import { AssigneePicker } from "./assignee-picker";
import { ItemForm } from "./item-form";

export interface SlipActions {
  /** Present when items themselves can be changed (manual entry, review). */
  updateItem?: (item: BillItem, body: BillItemCreate) => Promise<boolean>;
  deleteItem?: (item: BillItem) => Promise<void>;
  /** Present when who-had-what can be changed (review, open). */
  setAssignees?: (item: BillItem, personIds: string[]) => Promise<void>;
}

export function ReceiptSlip({
  bill,
  people,
  participants,
  actions,
  footer,
}: {
  bill: BillDetail;
  /** Everyone in the group, for names. */
  people: Person[];
  /** People on this bill - the only ones an item can go to. */
  participants: Person[];
  actions: SlipActions;
  footer?: React.ReactNode;
}) {
  const names = new Map(people.map((p) => [p.id, p.display_name]));
  const [editing, setEditing] = useState<{ itemId: string; mode: "item" | "people" } | null>(null);

  return (
    <div className="receipt-edge rounded-t-xl border border-b-0 border-line bg-surface px-4 pt-4 shadow-[0_1px_0_var(--line)]">
      {bill.items.length === 0 ? (
        <p className="py-6 text-center text-sm text-muted">No items yet.</p>
      ) : (
        <ul className="divide-y divide-dashed divide-line-strong">
          {bill.items.map((item) => {
            const rawState = itemAssignmentState(item);
            // "Unsure - check this" only means something while reviewing;
            // once the split is confirmed, a guess was accepted as-is.
            const state =
              rawState === "guess-check" && bill.status !== "needs_review" ? "guess" : rawState;
            const isEditingItem = editing?.itemId === item.id && editing.mode === "item";
            const isEditingPeople = editing?.itemId === item.id && editing.mode === "people";
            if (isEditingItem && actions.updateItem) {
              return (
                <li key={item.id} className="py-3">
                  <ItemForm
                    initial={item}
                    submitLabel="Save item"
                    onCancel={() => setEditing(null)}
                    onSubmit={async (body) => {
                      const ok = await actions.updateItem!(item, body);
                      if (ok) setEditing(null);
                      return ok;
                    }}
                  />
                </li>
              );
            }
            return (
              <li key={item.id} className="py-3">
                <div className="flex items-baseline justify-between gap-3">
                  <div className="min-w-0">
                    <p className="font-semibold">{item.parsed_name}</p>
                    <p className="flex flex-wrap items-center gap-x-3 text-xs text-muted">
                      <span>
                        {item.quantity > 1 && (
                          <span className="amount">
                            {item.quantity} × {formatMoney(item.price)}{" "}
                          </span>
                        )}
                        {item.base_type && BASE_TYPE_LABELS[item.base_type]}
                      </span>
                      {actions.updateItem && !isEditingPeople && (
                        <button
                          type="button"
                          onClick={() => setEditing({ itemId: item.id, mode: "item" })}
                          className="font-semibold text-ink-soft underline-offset-2 hover:text-ink hover:underline"
                        >
                          Edit item
                        </button>
                      )}
                      {actions.deleteItem && !isEditingPeople && (
                        <DeleteItem onDelete={() => actions.deleteItem!(item)} />
                      )}
                    </p>
                  </div>
                  <span className="amount shrink-0 font-semibold">
                    {formatCents(lineTotalCents(item))}
                  </span>
                </div>

                <div className="mt-2 flex items-center justify-between gap-2">
                  <Assignees item={item} names={names} state={state} />
                  {actions.setAssignees && !isEditingPeople && (
                    <Button
                      type="button"
                      variant="secondary"
                      className="shrink-0 !px-3 !py-1"
                      onClick={() => setEditing({ itemId: item.id, mode: "people" })}
                    >
                      {state === "unassigned" ? "Choose who" : "Change"}
                    </Button>
                  )}
                </div>

                {isEditingPeople && actions.setAssignees && (
                  <AssigneePicker
                    people={participants}
                    current={item.assignments.map((a) => a.person_id)}
                    onCancel={() => setEditing(null)}
                    onSave={async (ids) => {
                      await actions.setAssignees!(item, ids);
                      setEditing(null);
                    }}
                  />
                )}
              </li>
            );
          })}
        </ul>
      )}

      <Totals bill={bill} />
      {footer}
    </div>
  );
}

function Assignees({
  item,
  names,
  state,
}: {
  item: BillItem;
  names: Map<string, string>;
  state: ReturnType<typeof itemAssignmentState>;
}) {
  if (state === "unassigned") {
    return (
      <span className="rounded bg-highlight px-2 py-0.5 text-sm font-semibold text-highlight-ink">
        Nobody yet - choose who had this
      </span>
    );
  }
  return (
    <span
      className={`flex flex-wrap items-center gap-1.5 rounded-full py-0.5 pl-0.5 pr-2 text-sm ${
        state === "guess-check" ? "bg-highlight text-highlight-ink" : ""
      }`}
    >
      {item.assignments.map((a) => {
        const name = names.get(a.person_id) ?? "Someone";
        return (
          <span key={a.id} className="flex items-center gap-1.5">
            <Avatar name={name} size="sm" />
            <span className="font-medium">{name}</span>
          </span>
        );
      })}
      <span className="text-xs opacity-80">
        {state === "shared" && "shared equally"}
        {state === "guess" && "guessed"}
        {state === "guess-check" && "unsure - check this"}
      </span>
    </span>
  );
}

function DeleteItem({ onDelete }: { onDelete: () => Promise<void> }) {
  const [asking, setAsking] = useState(false);
  const [busy, setBusy] = useState(false);
  const link = "font-semibold underline-offset-2 hover:underline";
  if (!asking) {
    return (
      <button type="button" onClick={() => setAsking(true)} className={`${link} text-ink-soft`}>
        Remove
      </button>
    );
  }
  return (
    <span className="inline-flex items-center gap-3">
      <button
        type="button"
        disabled={busy}
        className={`${link} text-danger`}
        onClick={async () => {
          setBusy(true);
          await onDelete();
          setBusy(false);
          setAsking(false);
        }}
      >
        {busy ? "Removing…" : "Yes, remove line"}
      </button>
      <button type="button" onClick={() => setAsking(false)} className={`${link} text-ink-soft`}>
        Keep
      </button>
    </span>
  );
}

function Totals({ bill }: { bill: BillDetail }) {
  const rows: [string, string | null][] = [
    ["Items", bill.subtotal],
    ["Tax", bill.tax_total],
    ["Tip / service", bill.tip_total],
  ];
  return (
    <dl className="mt-2 border-t-2 border-dashed border-line-strong pt-3 text-sm">
      {rows.map(([label, value]) => (
        <div key={label} className="flex justify-between py-0.5 text-ink-soft">
          <dt>{label}</dt>
          <dd className="amount">{formatMoney(value)}</dd>
        </div>
      ))}
      <div className="mt-1 flex justify-between text-base font-bold">
        <dt>Total</dt>
        <dd className="amount">{formatMoney(bill.grand_total)}</dd>
      </div>
    </dl>
  );
}
