"use client";

// Choose who had an item (Blocks 7-8). Tapping one name gives the item to
// that person; "Shared" lets several people be picked and splits the cost
// evenly (design.md §7). Either way the change goes back to the server as a
// correction, which is what teaches BillSplit people's tastes (design.md §8).

import type { Person } from "@billsplit/shared-types";
import { useState } from "react";

import { Avatar, Button } from "@/components/ui";

export function AssigneePicker({
  people,
  current,
  onSave,
  onCancel,
}: {
  people: Person[];
  current: string[];
  onSave: (personIds: string[]) => Promise<void>;
  onCancel: () => void;
}) {
  const [shared, setShared] = useState(current.length > 1);
  const [selected, setSelected] = useState<string[]>(current);
  const [saving, setSaving] = useState(false);

  async function save(ids: string[]) {
    setSaving(true);
    await onSave(ids);
    setSaving(false);
  }

  function tap(personId: string) {
    if (!shared) {
      void save([personId]);
      return;
    }
    setSelected((prev) =>
      prev.includes(personId) ? prev.filter((id) => id !== personId) : [...prev, personId],
    );
  }

  return (
    <div className="mt-2 rounded-lg border border-line-strong bg-paper p-3">
      <div className="mb-2 flex items-center justify-between gap-3 text-sm">
        <span className="font-semibold">{shared ? "Who shared it?" : "Whose was it?"}</span>
        <label className="flex items-center gap-2 text-ink-soft">
          <input
            type="checkbox"
            checked={shared}
            onChange={(e) => {
              setShared(e.target.checked);
              if (!e.target.checked) setSelected(current.length === 1 ? current : []);
            }}
            className="size-4 accent-[var(--ink)]"
          />
          Shared
        </label>
      </div>
      <div
        className="flex flex-wrap gap-2"
        role="group"
        aria-label={shared ? "People who shared this item" : "Person who had this item"}
      >
        {people.map((person) => {
          const on = shared
            ? selected.includes(person.id)
            : current.length === 1 && current[0] === person.id;
          return (
            <button
              key={person.id}
              type="button"
              aria-pressed={on}
              disabled={saving}
              onClick={() => tap(person.id)}
              className={`flex items-center gap-2 rounded-full border py-1 pl-1 pr-3 text-sm transition ${
                on
                  ? "border-ink bg-ink text-paper"
                  : "border-line-strong bg-surface hover:border-ink"
              }`}
            >
              <Avatar name={person.display_name} size="sm" />
              {person.display_name}
            </button>
          );
        })}
      </div>
      <div className="mt-3 flex items-center gap-2">
        {shared && (
          <Button
            type="button"
            busy={saving}
            disabled={selected.length === 0}
            onClick={() => void save(selected)}
          >
            {selected.length > 1 ? `Split between ${selected.length}` : "Save"}
          </Button>
        )}
        <Button type="button" variant="quiet" onClick={onCancel} disabled={saving}>
          Cancel
        </Button>
      </div>
    </div>
  );
}
