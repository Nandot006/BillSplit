"use client";

import type { BillDetail, Person, PersonSplit } from "@billsplit/shared-types";
import { useState, type FormEvent } from "react";

import { Avatar, Button, Notice, inputClass } from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import { formatMoney, parseMoneyInput } from "@/lib/money";

/** Who was on this bill; add or remove people for just this bill (Block 9). */
export function ParticipantsPanel({
  bill,
  people,
  currentUserId,
  editable,
  onAdd,
  onRemove,
}: {
  bill: BillDetail;
  people: Person[];
  currentUserId: string;
  editable: boolean;
  onAdd: (personId: string) => Promise<void>;
  onRemove: (person: Person) => Promise<void>;
}) {
  const on = new Set(bill.participant_person_ids);
  const participants = people.filter((p) => on.has(p.id));
  const others = people.filter((p) => !on.has(p.id));
  const [busyId, setBusyId] = useState<string | null>(null);

  async function act(personId: string, fn: () => Promise<void>) {
    setBusyId(personId);
    await fn();
    setBusyId(null);
  }

  return (
    <div>
      <ul className="flex flex-wrap gap-2">
        {participants.map((person) => (
          <li
            key={person.id}
            className="flex items-center gap-2 rounded-full border border-line-strong bg-surface py-1 pl-1 pr-2 text-sm"
          >
            <Avatar name={person.display_name} size="sm" />
            {person.display_name}
            {person.supabase_user_id === currentUserId && <span className="text-muted">(you)</span>}
            {editable && participants.length > 1 && (
              <button
                type="button"
                aria-label={`Remove ${person.display_name} from this bill`}
                disabled={busyId !== null}
                onClick={() => act(person.id, () => onRemove(person))}
                className="ml-1 rounded-full px-1.5 text-muted hover:bg-danger-soft hover:text-danger"
              >
                {busyId === person.id ? "…" : "×"}
              </button>
            )}
          </li>
        ))}
      </ul>
      {editable && others.length > 0 && (
        <div className="mt-3 flex flex-wrap items-center gap-2 text-sm">
          <span className="text-muted">Add:</span>
          {others.map((person) => (
            <button
              key={person.id}
              type="button"
              disabled={busyId !== null}
              onClick={() => act(person.id, () => onAdd(person.id))}
              className="rounded-full border border-dashed border-line-strong px-3 py-1 text-ink-soft hover:border-ink hover:text-ink"
            >
              + {person.display_name}
            </button>
          ))}
        </div>
      )}
      {editable && (
        <p className="mt-3 text-xs text-muted">
          Removing someone moves their items to whoever else most likely had them, and re-splits tax
          and tip.
        </p>
      )}
    </div>
  );
}

/** Merchant, date, tax and tip. */
export function ChargesForm({
  bill,
  onSaved,
}: {
  bill: BillDetail;
  onSaved: () => Promise<unknown>;
}) {
  const [merchant, setMerchant] = useState(bill.merchant_name ?? "");
  const [date, setDate] = useState(bill.bill_date ?? "");
  const [tax, setTax] = useState(bill.tax_total ?? "");
  const [tip, setTip] = useState(bill.tip_total === "0.00" ? "" : bill.tip_total);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function save(event: FormEvent) {
    event.preventDefault();
    const taxValue = tax.trim() === "" ? "0.00" : parseMoneyInput(tax);
    const tipValue = tip.trim() === "" ? "0.00" : parseMoneyInput(tip);
    if (taxValue === null || tipValue === null) {
      setError("Tax and tip must be amounts like 45 or 45.50.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await api.updateBill(bill.id, {
        merchant_name: merchant.trim() || null,
        bill_date: date || null,
        tax_total: taxValue,
        tip_total: tipValue,
      });
      await onSaved();
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setSaving(false);
    }
  }

  return (
    <form onSubmit={save} className="flex flex-col gap-3">
      <div className="grid gap-3 sm:grid-cols-2">
        <label className="flex flex-col gap-1 text-sm">
          <span className="font-medium text-ink-soft">Where</span>
          <input
            value={merchant}
            onChange={(e) => setMerchant(e.target.value)}
            className={inputClass}
          />
        </label>
        <label className="flex flex-col gap-1 text-sm">
          <span className="font-medium text-ink-soft">Date</span>
          <input
            type="date"
            value={date}
            onChange={(e) => setDate(e.target.value)}
            className={inputClass}
          />
        </label>
        <label className="flex flex-col gap-1 text-sm">
          <span className="font-medium text-ink-soft">Total tax (all GST/VAT lines)</span>
          <input
            value={tax}
            onChange={(e) => setTax(e.target.value)}
            inputMode="decimal"
            placeholder="0.00"
            className={`${inputClass} amount`}
          />
        </label>
        <label className="flex flex-col gap-1 text-sm">
          <span className="font-medium text-ink-soft">Tip or service charge</span>
          <input
            value={tip}
            onChange={(e) => setTip(e.target.value)}
            inputMode="decimal"
            placeholder="0.00"
            className={`${inputClass} amount`}
          />
        </label>
      </div>
      <p className="text-xs text-muted">
        Tax and tip are split equally between everyone on the bill.
      </p>
      {error && <Notice tone="error">{error}</Notice>}
      <div>
        <Button type="submit" variant="secondary" busy={saving}>
          Save details
        </Button>
      </div>
    </form>
  );
}

/** Live per-person breakdown before the bill is confirmed. */
export function SplitPreview({ splits }: { splits: PersonSplit[] }) {
  return (
    <ul className="divide-y divide-line overflow-hidden rounded-xl border border-line bg-surface">
      {splits.map((s) => (
        <li key={s.person_id} className="flex items-center justify-between gap-3 px-4 py-3">
          <span className="flex items-center gap-2 font-medium">
            <Avatar name={s.display_name} size="sm" />
            {s.display_name}
          </span>
          <span className="text-right">
            <span className="amount block font-semibold">{formatMoney(s.total_owed)}</span>
            <span className="amount text-xs text-muted">
              items {formatMoney(s.item_subtotal_share)} + tax/tip{" "}
              {formatMoney(Number(s.tax_share) + Number(s.tip_share))}
            </span>
          </span>
        </li>
      ))}
    </ul>
  );
}

/** The receipt photo, fetched as a short-lived link only when asked for. */
export function ReceiptPhoto({ billId }: { billId: string }) {
  const [url, setUrl] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function show() {
    setLoading(true);
    setError(null);
    try {
      setUrl((await api.getBillImageUrl(billId)).url);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setLoading(false);
    }
  }

  if (url) {
    return (
      <figure className="overflow-hidden rounded-xl border border-line bg-surface">
        {/* eslint-disable-next-line @next/next/no-img-element -- signed, short-lived Storage URL */}
        <img src={url} alt="Photo of the receipt" className="max-h-[70vh] w-full object-contain" />
        <figcaption className="flex justify-end p-2">
          <Button type="button" variant="quiet" onClick={() => setUrl(null)}>
            Hide photo
          </Button>
        </figcaption>
      </figure>
    );
  }
  return (
    <div className="flex flex-col gap-2">
      <div>
        <Button type="button" variant="secondary" busy={loading} onClick={() => void show()}>
          Show receipt photo
        </Button>
      </div>
      {error && <Notice tone="error">{error}</Notice>}
    </div>
  );
}
