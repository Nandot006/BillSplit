"use client";

import { useRouter } from "next/navigation";
import { useRef, useState, type FormEvent } from "react";

import { useCurrentUser } from "@/components/current-user";
import { Avatar, Button, Field, Loading, Notice, PageHeader, Section } from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import {
  ACCEPT_ATTRIBUTE,
  prepareReceiptImage,
  uploadReceipt,
  validateReceiptFile,
} from "@/lib/receipt-image";
import { useResource } from "@/lib/use-resource";

type Step = "idle" | "preparing" | "uploading" | "creating";

const STEP_LABELS: Record<Step, string> = {
  idle: "",
  preparing: "Preparing photo",
  uploading: "Uploading photo",
  creating: "Starting the bill",
};

export function NewBillScreen({ groupId }: { groupId: string }) {
  const router = useRouter();
  const user = useCurrentUser();
  const group = useResource(() => api.getGroup(groupId), [groupId], { refetchOnFocus: false });
  // null = untouched, meaning "everyone"; a Set once they've changed it.
  const [picked, setPicked] = useState<Set<string> | null>(null);
  const [step, setStep] = useState<Step>("idle");
  const [error, setError] = useState<string | null>(null);
  const [merchant, setMerchant] = useState("");
  const [date, setDate] = useState("");
  const fileInput = useRef<HTMLInputElement>(null);
  const cameraInput = useRef<HTMLInputElement>(null);

  if (group.loading && !group.data) return <Loading label="Loading group" />;
  if (!group.data)
    return <Notice tone="error">{group.error ?? "Couldn't load this group."}</Notice>;

  const people = [...group.data.people].sort((a, b) =>
    a.supabase_user_id === user.id
      ? -1
      : b.supabase_user_id === user.id
        ? 1
        : a.display_name.localeCompare(b.display_name),
  );
  const selected = picked ?? new Set(people.map((p) => p.id));
  const busy = step !== "idle";

  function toggle(personId: string) {
    const next = new Set(selected);
    if (next.has(personId)) next.delete(personId);
    else next.add(personId);
    setPicked(next);
  }

  function participantIds(): string[] | null {
    if (selected.size === 0) {
      setError("Pick at least one person who was there.");
      return null;
    }
    return people.filter((p) => selected.has(p.id)).map((p) => p.id);
  }

  async function startWithPhoto(file: File) {
    setError(null);
    const problem = validateReceiptFile(file);
    if (problem) {
      setError(problem);
      return;
    }
    const ids = participantIds();
    if (!ids) return;
    try {
      setStep("preparing");
      const image = await prepareReceiptImage(file);
      setStep("uploading");
      const path = await uploadReceipt(user.id, image);
      setStep("creating");
      const bill = await api.createBill(groupId, {
        image_storage_path: path,
        participant_person_ids: ids,
      });
      router.push(`/bills/${bill.id}`);
    } catch (e) {
      setError(errorMessage(e));
      setStep("idle");
    }
  }

  async function startManual(event: FormEvent) {
    event.preventDefault();
    setError(null);
    const ids = participantIds();
    if (!ids) return;
    try {
      setStep("creating");
      const bill = await api.createBill(groupId, {
        merchant_name: merchant.trim() || null,
        bill_date: date || null,
        participant_person_ids: ids,
      });
      router.push(`/bills/${bill.id}`);
    } catch (e) {
      setError(errorMessage(e));
      setStep("idle");
    }
  }

  return (
    <>
      <PageHeader title="New bill" back={{ href: `/groups/${groupId}`, label: group.data.name }} />

      <Section
        title="Who was there?"
        aside={<span className="text-sm text-muted">{selected.size} selected</span>}
      >
        <p className="mb-3 text-sm text-ink-soft">
          Items, tax and tip are only split between these people.
        </p>
        <ul className="flex flex-wrap gap-2">
          {people.map((person) => {
            const on = selected.has(person.id);
            return (
              <li key={person.id}>
                <button
                  type="button"
                  aria-pressed={on}
                  onClick={() => toggle(person.id)}
                  disabled={busy}
                  className={`flex items-center gap-2 rounded-full border py-1 pl-1 pr-3 text-sm transition ${
                    on
                      ? "border-ink bg-ink text-paper"
                      : "border-line-strong bg-surface text-ink-soft line-through decoration-1"
                  }`}
                >
                  <Avatar name={person.display_name} size="sm" />
                  {person.display_name}
                  {person.supabase_user_id === user.id && " (you)"}
                </button>
              </li>
            );
          })}
        </ul>
      </Section>

      <Section title="Add the receipt">
        {[
          { ref: cameraInput, capture: true },
          { ref: fileInput, capture: false },
        ].map(({ ref, capture }) => (
          <input
            key={String(capture)}
            ref={ref}
            type="file"
            accept={ACCEPT_ATTRIBUTE}
            // capture opens the phone camera directly; the other input is a
            // normal picker for a photo already taken (or desktop files).
            capture={capture ? "environment" : undefined}
            className="sr-only"
            tabIndex={-1}
            aria-hidden
            onChange={(e) => {
              const file = e.target.files?.[0];
              e.target.value = "";
              if (file) void startWithPhoto(file);
            }}
          />
        ))}
        <div className="rounded-xl border border-line bg-surface p-5">
          {busy && step !== "creating" ? (
            <p role="status" className="flex items-center gap-3 font-semibold">
              <span className="size-4 animate-spin rounded-full border-2 border-line-strong border-t-ink motion-reduce:animate-none" />
              {STEP_LABELS[step]}…
            </p>
          ) : (
            <div className="flex flex-col gap-2 sm:flex-row">
              <Button type="button" onClick={() => cameraInput.current?.click()} disabled={busy}>
                Take photo
              </Button>
              <Button
                type="button"
                variant="secondary"
                onClick={() => fileInput.current?.click()}
                disabled={busy}
              >
                Choose photo
              </Button>
            </div>
          )}
          <p className="mt-3 text-sm text-ink-soft">
            JPEG, PNG or HEIC, up to 10 MB. BillSplit reads the items and guesses who had each one -
            you check the guesses before anything is final.
          </p>
        </div>

        <details className="mt-4 rounded-xl border border-line bg-surface p-5 [&_summary]:cursor-pointer">
          <summary className="font-semibold">No photo? Type the bill in</summary>
          <form onSubmit={startManual} className="mt-4 flex flex-col gap-4">
            <Field
              label="Where (optional)"
              value={merchant}
              onChange={(e) => setMerchant(e.target.value)}
              placeholder="e.g. Annapoorna"
              disabled={busy}
            />
            <Field
              label="Date (optional)"
              type="date"
              value={date}
              onChange={(e) => setDate(e.target.value)}
              disabled={busy}
            />
            <div>
              <Button type="submit" variant="secondary" busy={step === "creating"}>
                Start typing items
              </Button>
            </div>
          </form>
        </details>
      </Section>

      {error && <Notice tone="error">{error}</Notice>}
    </>
  );
}
