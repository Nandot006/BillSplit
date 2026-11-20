"use client";

// Add or edit one bill line: name, price, quantity, and optional tags that
// help the guesses (dish type, flavors, dietary). Used for typing a bill in
// and for fixing a misread line while reviewing.

import {
  BASE_TYPES,
  DIETARY_FLAGS,
  FLAVOR_TAGS,
  type BaseType,
  type BillItem,
  type BillItemCreate,
  type DietaryFlag,
  type FlavorTag,
} from "@billsplit/shared-types";
import { useState, type FormEvent } from "react";

import { Button, Notice, inputClass } from "@/components/ui";
import { parseMoneyInput } from "@/lib/money";
import { BASE_TYPE_LABELS, DIETARY_LABELS, FLAVOR_LABELS } from "@/lib/taxonomy";

export function ItemForm({
  initial,
  submitLabel,
  onSubmit,
  onCancel,
}: {
  initial?: BillItem;
  submitLabel: string;
  onSubmit: (body: BillItemCreate) => Promise<boolean>;
  onCancel?: () => void;
}) {
  const [name, setName] = useState(initial?.parsed_name ?? "");
  const [price, setPrice] = useState(initial?.price ?? "");
  const [quantity, setQuantity] = useState(String(initial?.quantity ?? 1));
  const [baseType, setBaseType] = useState<BaseType | "">(initial?.base_type ?? "");
  const [flavors, setFlavors] = useState<FlavorTag[]>(initial?.flavor_tags ?? []);
  const [dietary, setDietary] = useState<DietaryFlag[]>(initial?.dietary_flags ?? []);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const hasTags = Boolean(
    initial?.base_type || initial?.flavor_tags.length || initial?.dietary_flags.length,
  );

  async function submit(event: FormEvent) {
    event.preventDefault();
    const parsedPrice = parseMoneyInput(price);
    const qty = Number(quantity);
    if (!name.trim()) return setError("Give the item a name.");
    if (parsedPrice === null) return setError("Enter the price as a number, like 120 or 85.50.");
    if (!Number.isInteger(qty) || qty < 1)
      return setError("Quantity must be a whole number, 1 or more.");
    setError(null);
    setSaving(true);
    const ok = await onSubmit({
      parsed_name: name.trim(),
      price: parsedPrice,
      quantity: qty,
      base_type: baseType || null,
      flavor_tags: flavors,
      dietary_flags: dietary,
    });
    setSaving(false);
    if (ok && !initial) {
      setName("");
      setPrice("");
      setQuantity("1");
      setBaseType("");
      setFlavors([]);
      setDietary([]);
    }
  }

  return (
    <form onSubmit={submit} className="flex flex-col gap-3" aria-label={submitLabel}>
      <div className="grid grid-cols-[1fr_6.5rem_4.5rem] gap-2">
        <label className="flex flex-col gap-1 text-sm">
          <span className="font-medium text-ink-soft">Item</span>
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            maxLength={300}
            className={inputClass}
            placeholder="Masala dosa"
          />
        </label>
        <label className="flex flex-col gap-1 text-sm">
          <span className="font-medium text-ink-soft">Price each</span>
          <input
            value={price}
            onChange={(e) => setPrice(e.target.value)}
            inputMode="decimal"
            className={`${inputClass} amount text-right`}
            placeholder="0.00"
          />
        </label>
        <label className="flex flex-col gap-1 text-sm">
          <span className="font-medium text-ink-soft">Qty</span>
          <input
            value={quantity}
            onChange={(e) => setQuantity(e.target.value)}
            inputMode="numeric"
            className={`${inputClass} amount text-right`}
          />
        </label>
      </div>

      <details open={hasTags} className="text-sm">
        <summary className="cursor-pointer text-ink-soft">
          Describe the dish (helps the guesses)
        </summary>
        <div className="mt-3 flex flex-col gap-3">
          <label className="flex flex-col gap-1">
            <span className="font-medium text-ink-soft">Kind of item</span>
            <select
              value={baseType}
              onChange={(e) => setBaseType(e.target.value as BaseType | "")}
              className={inputClass}
            >
              <option value="">Not sure</option>
              {BASE_TYPES.map((t) => (
                <option key={t} value={t}>
                  {BASE_TYPE_LABELS[t]}
                </option>
              ))}
            </select>
          </label>
          <TagPicker
            legend="Flavors"
            options={FLAVOR_TAGS}
            labels={FLAVOR_LABELS}
            value={flavors}
            onChange={setFlavors}
          />
          <p className="text-xs text-muted">
            Tick everything that applies. Someone with a dietary restriction (say, doesn&apos;t
            drink, or avoids pork) is only ever guessed for items ticked as suitable for them.
          </p>
          <TagPicker
            legend="Suitable for"
            options={DIETARY_FLAGS}
            labels={DIETARY_LABELS}
            value={dietary}
            onChange={setDietary}
          />
        </div>
      </details>

      {error && <Notice tone="error">{error}</Notice>}
      <div className="flex gap-2">
        <Button type="submit" variant={initial ? "primary" : "secondary"} busy={saving}>
          {submitLabel}
        </Button>
        {onCancel && (
          <Button type="button" variant="quiet" onClick={onCancel}>
            Cancel
          </Button>
        )}
      </div>
    </form>
  );
}

function TagPicker<T extends string>({
  legend,
  options,
  labels,
  value,
  onChange,
}: {
  legend: string;
  options: readonly T[];
  labels: Record<T, string>;
  value: T[];
  onChange: (next: T[]) => void;
}) {
  return (
    <fieldset>
      <legend className="mb-1 font-medium text-ink-soft">{legend}</legend>
      <div className="flex flex-wrap gap-1.5">
        {options.map((option) => {
          const on = value.includes(option);
          return (
            <button
              key={option}
              type="button"
              aria-pressed={on}
              onClick={() => onChange(on ? value.filter((v) => v !== option) : [...value, option])}
              className={`rounded-full border px-2.5 py-0.5 ${on ? "border-ink bg-ink text-paper" : "border-line-strong text-ink-soft hover:border-ink"}`}
            >
              {labels[option]}
            </button>
          );
        })}
      </div>
    </fieldset>
  );
}
