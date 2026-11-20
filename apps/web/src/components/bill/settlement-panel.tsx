"use client";

// Payer, who owes what, and the payer-controlled "paid" marks (Blocks
// 10-11, design.md §11-12). Closing is only offered once a payer is set and
// everyone else is marked paid; after that the bill is read-only.

import type { BillDetail, PayerSuggestion, Person, SettlementRow } from "@billsplit/shared-types";
import { useState } from "react";

import { Avatar, Button, Notice, inputClass } from "@/components/ui";
import { closeReadiness, outstandingCents } from "@/lib/bill";
import { formatCents, formatMoney } from "@/lib/money";

export function SettlementPanel({
  bill,
  people,
  settlement,
  suggestion,
  onSetPayer,
  onSetPaid,
  onClose,
}: {
  bill: BillDetail;
  people: Person[];
  settlement: SettlementRow[];
  suggestion: PayerSuggestion | null;
  onSetPayer: (personId: string | null) => Promise<void>;
  onSetPaid: (personId: string, paid: boolean) => Promise<void>;
  onClose: () => Promise<void>;
}) {
  const closed = bill.status === "closed";
  const payerId = bill.payer_person_id;
  const payerName = people.find((p) => p.id === payerId)?.display_name;
  const readiness = closeReadiness(payerId, settlement);
  const owed = outstandingCents(payerId, settlement);
  const [busy, setBusy] = useState<string | null>(null);

  async function act(key: string, fn: () => Promise<void>) {
    setBusy(key);
    await fn();
    setBusy(null);
  }

  return (
    <div className="flex flex-col gap-4">
      {closed ? (
        <p className="text-ink-soft">
          {payerName ? (
            <>
              <strong className="text-ink">{payerName}</strong> paid, and everyone has paid them
              back.
            </>
          ) : (
            "Settled."
          )}
        </p>
      ) : (
        <PayerChooser
          people={people}
          bill={bill}
          suggestion={suggestion}
          busy={busy === "payer"}
          onSave={(id) => act("payer", () => onSetPayer(id))}
        />
      )}

      <ul className="divide-y divide-line overflow-hidden rounded-xl border border-line bg-surface">
        {settlement.map((row) => {
          const isPayer = row.person_id === payerId;
          return (
            <li key={row.person_id} className="flex items-center justify-between gap-3 px-4 py-3">
              <span className="flex min-w-0 items-center gap-2">
                <Avatar name={row.display_name} size="sm" />
                <span className="min-w-0">
                  <span className="block truncate font-medium">{row.display_name}</span>
                  <span className="text-xs text-muted">
                    {isPayer
                      ? "Paid the bill - their own share"
                      : payerId
                        ? `Owes ${payerName}`
                        : "Owes the payer"}
                  </span>
                </span>
              </span>
              <span className="flex shrink-0 items-center gap-3">
                <span className="amount font-semibold">{formatMoney(row.total_owed)}</span>
                {!isPayer &&
                  payerId &&
                  (row.is_paid ? (
                    <PaidStamp
                      onUndo={
                        closed
                          ? undefined
                          : () => act(row.person_id, () => onSetPaid(row.person_id, false))
                      }
                      busy={busy === row.person_id}
                    />
                  ) : (
                    !closed && (
                      <Button
                        type="button"
                        variant="secondary"
                        busy={busy === row.person_id}
                        onClick={() => act(row.person_id, () => onSetPaid(row.person_id, true))}
                      >
                        Mark paid
                      </Button>
                    )
                  ))}
              </span>
            </li>
          );
        })}
      </ul>

      {!closed && (
        <div className="flex flex-col gap-2 rounded-xl border border-line bg-surface p-4">
          {payerId && owed > 0 && (
            <p className="text-sm text-ink-soft">
              Still owed to {payerName}:{" "}
              <span className="amount font-semibold text-ink">{formatCents(owed)}</span>
            </p>
          )}
          <div>
            <Button
              type="button"
              busy={busy === "close"}
              disabled={!readiness.canClose}
              onClick={() => act("close", onClose)}
            >
              Close bill
            </Button>
          </div>
          <p className="text-sm text-muted">
            {readiness.reason ?? "Everyone's paid. Closing locks the bill so it can't be changed."}
          </p>
        </div>
      )}
    </div>
  );
}

function PaidStamp({ onUndo, busy }: { onUndo?: () => void; busy: boolean }) {
  return (
    <span className="flex items-center gap-2">
      <span className="stamp stamp-in px-2 py-0.5 text-sm font-bold text-stamp">PAID</span>
      {onUndo && (
        <button
          type="button"
          onClick={onUndo}
          disabled={busy}
          className="text-xs text-muted underline-offset-2 hover:underline"
        >
          {busy ? "…" : "Undo"}
        </button>
      )}
    </span>
  );
}

function PayerChooser({
  people,
  bill,
  suggestion,
  busy,
  onSave,
}: {
  people: Person[];
  bill: BillDetail;
  suggestion: PayerSuggestion | null;
  busy: boolean;
  onSave: (personId: string | null) => void;
}) {
  const on = new Set(bill.participant_person_ids);
  // Participants first (the usual payer), then anyone else in the group -
  // someone can pay for a meal they didn't eat.
  const ordered = [...people.filter((p) => on.has(p.id)), ...people.filter((p) => !on.has(p.id))];
  const [choice, setChoice] = useState<string>(bill.payer_person_id ?? suggestion?.person_id ?? "");
  const dirty = choice !== (bill.payer_person_id ?? "");

  return (
    <div className="rounded-xl border border-line bg-surface p-4">
      <label htmlFor="payer" className="mb-1 block font-semibold">
        Who paid the bill?
      </label>
      {!bill.payer_person_id && suggestion && (
        <p className="mb-2 text-sm text-ink-soft">
          Suggested: {suggestion.display_name}, who paid least recently in this group.
        </p>
      )}
      <div className="flex flex-col gap-2 sm:flex-row">
        <select
          id="payer"
          value={choice}
          onChange={(e) => setChoice(e.target.value)}
          className={`${inputClass} flex-1`}
        >
          <option value="">Choose…</option>
          {ordered.map((p) => (
            <option key={p.id} value={p.id}>
              {p.display_name}
              {!on.has(p.id) ? " (not on this bill)" : ""}
            </option>
          ))}
        </select>
        <Button
          type="button"
          busy={busy}
          disabled={!dirty || !choice}
          onClick={() => onSave(choice)}
        >
          {bill.payer_person_id ? "Change payer" : "Set payer"}
        </Button>
      </div>
      {bill.payer_person_id && dirty && (
        <div className="mt-2">
          <Notice tone="info">Changing the payer keeps anyone already marked paid.</Notice>
        </div>
      )}
    </div>
  );
}
