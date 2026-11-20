"use client";

// One bill, start to finish (Phase 2 Blocks 6-11). What's shown follows the
// bill's status:
//   processing          -> waiting for the receipt to be read (polls)
//   needs_manual_entry  -> type the items in
//   needs_review        -> check/fix who had what, fix misread lines
//   open                -> settle up: payer, who's paid, close
//   closed              -> read-only record
// The screen re-fetches when you come back to the tab (auto-refresh on
// focus), so edits made on another device show up.

import type {
  BillDetail,
  BillItem,
  BillItemCreate,
  GroupDetail,
  PayerSuggestion,
  Person,
  PersonSplit,
  SettlementRow,
} from "@billsplit/shared-types";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { ItemForm } from "@/components/bill/item-form";
import {
  ChargesForm,
  ParticipantsPanel,
  ReceiptPhoto,
  SplitPreview,
} from "@/components/bill/panels";
import { ReceiptSlip, type SlipActions } from "@/components/bill/receipt-slip";
import { SettlementPanel } from "@/components/bill/settlement-panel";
import { ConfirmButton } from "@/components/confirm-button";
import { useCurrentUser } from "@/components/current-user";
import { Button, Loading, Notice, PageHeader, Section } from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import { STATUS_LABELS, reviewSummary } from "@/lib/bill";
import { useResource } from "@/lib/use-resource";

interface BillData {
  bill: BillDetail;
  group: GroupDetail;
  splits: PersonSplit[] | null;
  settlement: SettlementRow[] | null;
  suggestion: PayerSuggestion | null;
}

async function loadBill(billId: string): Promise<BillData> {
  const bill = await api.getBill(billId);
  const [group, splits, settlement, suggestion] = await Promise.all([
    api.getGroup(bill.group_id),
    bill.status === "needs_review" ? api.getSplits(billId) : Promise.resolve(null),
    bill.status === "open" || bill.status === "closed"
      ? api.getSettlement(billId)
      : Promise.resolve(null),
    bill.status === "open" && !bill.payer_person_id
      ? api.getPayerSuggestion(billId).catch(() => null)
      : Promise.resolve(null),
  ]);
  return { bill, group, splits, settlement, suggestion };
}

export function BillScreen({ billId }: { billId: string }) {
  const user = useCurrentUser();
  const [processing, setProcessing] = useState(false);
  const resource = useResource(() => loadBill(billId), [billId], {
    pollMs: processing ? 3000 : undefined,
  });
  const status = resource.data?.bill.status;
  useEffect(() => {
    // Poll only while the receipt is being read; stop as soon as it's done.
    // (A state update in response to fetched data, not a render loop.)
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setProcessing(status === "processing");
  }, [status]);

  const [toast, setToast] = useState<{ tone: "success" | "error"; text: string } | null>(null);
  const toastTimer = useRef<number | undefined>(undefined);
  function say(tone: "success" | "error", text: string) {
    window.clearTimeout(toastTimer.current);
    setToast({ tone, text });
    toastTimer.current = window.setTimeout(() => setToast(null), tone === "error" ? 8000 : 4000);
  }

  /** Runs a change, reloads the bill, and reports the outcome. */
  async function run(fn: () => Promise<unknown>, success?: string): Promise<boolean> {
    try {
      await fn();
      await resource.reload();
      if (success) say("success", success);
      return true;
    } catch (e) {
      say("error", errorMessage(e));
      await resource.reload();
      return false;
    }
  }

  if (resource.loading && !resource.data) return <Loading label="Loading bill" />;
  if (!resource.data)
    return <Notice tone="error">{resource.error ?? "Couldn't load this bill."}</Notice>;

  const { bill, group, splits, settlement, suggestion } = resource.data;
  const people = group.people;
  const onBill = new Set(bill.participant_person_ids);
  const participants = people.filter((p) => onBill.has(p.id));
  const nameOf = (id: string) => people.find((p) => p.id === id)?.display_name ?? "Someone";

  const title =
    bill.merchant_name || (bill.status === "processing" ? "Reading receipt…" : "Untitled bill");
  const subtitle = [
    bill.bill_date
      ? new Date(`${bill.bill_date}T00:00:00`).toLocaleDateString(undefined, {
          dateStyle: "medium",
        })
      : null,
    STATUS_LABELS[bill.status],
  ]
    .filter(Boolean)
    .join(" · ");

  const itemActions: SlipActions = {
    updateItem: (item: BillItem, body: BillItemCreate) =>
      run(() => api.updateItem(bill.id, item.id, body), "Item updated."),
    deleteItem: async (item: BillItem) => {
      await run(() => api.deleteItem(bill.id, item.id), `Removed "${item.parsed_name}".`);
    },
  };
  const assignAction: SlipActions["setAssignees"] = async (item, ids) => {
    const message =
      ids.length === 1
        ? `${nameOf(ids[0])} had ${item.parsed_name}. BillSplit will remember.`
        : `${item.parsed_name} split between ${ids.map(nameOf).join(", ")}.`;
    await run(() => api.setItemAssignees(bill.id, item.id, ids), message);
  };
  const participantsPanel = (
    <ParticipantsPanel
      bill={bill}
      people={people}
      currentUserId={user.id}
      editable={bill.status !== "closed"}
      onAdd={async (personId) => {
        await run(
          () => api.addParticipant(bill.id, personId),
          `${nameOf(personId)} added to this bill.`,
        );
      }}
      onRemove={async (person: Person) => {
        await run(
          () => api.removeParticipant(bill.id, person.id),
          `${person.display_name} removed. Their items were reassigned - check them below.`,
        );
      }}
    />
  );

  return (
    <>
      <PageHeader title={title} back={{ href: `/groups/${group.id}`, label: group.name }}>
        <p className="text-sm text-ink-soft">{subtitle}</p>
      </PageHeader>

      {toast && (
        <div className="sticky top-2 z-10 mb-4">
          <Notice tone={toast.tone}>{toast.text}</Notice>
        </div>
      )}
      {resource.error && (
        <div className="mb-4">
          <Notice tone="error">{resource.error}</Notice>
        </div>
      )}

      {bill.status === "processing" && (
        <ProcessingView
          createdAt={bill.created_at}
          onManual={() => run(() => api.switchToManualEntry(bill.id))}
        />
      )}

      {bill.status === "needs_manual_entry" && (
        <>
          {bill.image_storage_path && (
            <div className="mb-6 flex flex-col gap-3">
              <Notice tone="attention">
                The receipt couldn&apos;t be read automatically. Type the items in below - the photo
                is here to copy from.
              </Notice>
              <ReceiptPhoto billId={bill.id} />
            </div>
          )}
          <Section title="Items">
            <ReceiptSlip
              bill={bill}
              people={people}
              participants={participants}
              actions={itemActions}
            />
            <div className="mt-4 rounded-xl border border-line bg-surface p-4">
              <ItemForm
                submitLabel="Add item"
                onSubmit={(body) => run(() => api.addItem(bill.id, body))}
              />
            </div>
          </Section>
          <Section title="Details, tax and tip">
            <ChargesForm
              key={bill.id + bill.tax_total + bill.tip_total}
              bill={bill}
              onSaved={() => run(async () => {}, "Saved.")}
            />
          </Section>
          <Section title="Who was there">{participantsPanel}</Section>
          <div className="flex flex-col gap-2 rounded-xl border border-line bg-surface p-4">
            <div>
              <Button
                type="button"
                disabled={bill.items.length === 0}
                onClick={() =>
                  run(() => api.finalizeManualEntry(bill.id), "Done. Check the guesses below.")
                }
              >
                Guess who had what
              </Button>
            </div>
            <p className="text-sm text-muted">
              {bill.items.length === 0
                ? "Add at least one item first."
                : "BillSplit guesses each item's owner from everyone's tastes. You can change any guess."}
            </p>
          </div>
        </>
      )}

      {bill.status === "needs_review" && (
        <ReviewView
          bill={bill}
          people={people}
          participants={participants}
          splits={splits ?? []}
          itemActions={{ ...itemActions, setAssignees: assignAction }}
          participantsPanel={participantsPanel}
          run={run}
        />
      )}

      {(bill.status === "open" || bill.status === "closed") && (
        <>
          <Section title={bill.status === "closed" ? "Settlement" : "Settle up"}>
            <SettlementPanel
              bill={bill}
              people={people}
              settlement={settlement ?? []}
              suggestion={suggestion}
              onSetPayer={async (id) => {
                await run(
                  () => api.setPayer(bill.id, id),
                  id ? `${nameOf(id)} is the payer.` : undefined,
                );
              }}
              onSetPaid={async (personId, paid) => {
                await run(
                  () => api.setPaid(bill.id, personId, paid),
                  paid
                    ? `${nameOf(personId)} marked as paid.`
                    : `${nameOf(personId)} marked as not paid.`,
                );
              }}
              onClose={async () => {
                await run(() => api.closeBill(bill.id), "Bill closed. It's settled and locked.");
              }}
            />
          </Section>
          <Section title="Who had what">
            {bill.status === "open" && (
              <p className="mb-3 text-sm text-ink-soft">
                Items are locked now, but you can still change who had what. Amounts above update to
                match.
              </p>
            )}
            <ReceiptSlip
              bill={bill}
              people={people}
              participants={participants}
              actions={bill.status === "open" ? { setAssignees: assignAction } : {}}
            />
          </Section>
          <Section title="Who was there">{participantsPanel}</Section>
          {bill.image_storage_path && (
            <Section title="Receipt">
              <ReceiptPhoto billId={bill.id} />
            </Section>
          )}
        </>
      )}

      {bill.status !== "closed" && bill.status !== "processing" && (
        <DeleteBill billId={bill.id} groupId={group.id} />
      )}
    </>
  );
}

function ReviewView({
  bill,
  people,
  participants,
  splits,
  itemActions,
  participantsPanel,
  run,
}: {
  bill: BillDetail;
  people: Person[];
  participants: Person[];
  splits: PersonSplit[];
  itemActions: SlipActions;
  participantsPanel: React.ReactNode;
  run: (fn: () => Promise<unknown>, success?: string) => Promise<boolean>;
}) {
  const [adding, setAdding] = useState(false);
  const summary = reviewSummary(bill);

  return (
    <>
      <div className="mb-6">
        {summary.unassigned > 0 ? (
          <Notice tone="attention">
            {summary.unassigned} item{summary.unassigned === 1 ? " needs" : "s need"} someone chosen
            before you can confirm.
          </Notice>
        ) : summary.toCheck > 0 ? (
          <Notice tone="attention">
            BillSplit was unsure about {summary.toCheck} item{summary.toCheck === 1 ? "" : "s"}{" "}
            (highlighted). Every fix you make teaches it.
          </Notice>
        ) : (
          <Notice tone="info">
            Check each line. Tap Change if a guess is wrong, or if an item was shared.
          </Notice>
        )}
      </div>

      <Section title="Who had what">
        <ReceiptSlip
          bill={bill}
          people={people}
          participants={participants}
          actions={itemActions}
          footer={
            <div className="mt-3">
              {adding ? (
                <ItemForm
                  submitLabel="Add item"
                  onCancel={() => setAdding(false)}
                  onSubmit={async (body) => {
                    const ok = await run(
                      () => api.addItem(bill.id, body),
                      `Added "${body.parsed_name}".`,
                    );
                    if (ok) setAdding(false);
                    return ok;
                  }}
                />
              ) : (
                <Button type="button" variant="quiet" onClick={() => setAdding(true)}>
                  + Add a line the receipt missed
                </Button>
              )}
            </div>
          }
        />
      </Section>

      {bill.image_storage_path && (
        <Section title="Receipt">
          <ReceiptPhoto billId={bill.id} />
        </Section>
      )}

      <Section title="Who was there">{participantsPanel}</Section>

      <Section title="Details, tax and tip">
        <ChargesForm
          key={bill.id + bill.tax_total + bill.tip_total}
          bill={bill}
          onSaved={() => run(async () => {}, "Saved.")}
        />
      </Section>

      <Section title="Each person's share">
        <SplitPreview splits={splits} />
      </Section>

      <div className="flex flex-col gap-2 rounded-xl border border-line bg-surface p-4">
        <div>
          <Button
            type="button"
            disabled={summary.unassigned > 0}
            onClick={() => run(() => api.confirmBill(bill.id), "Confirmed. Now settle up.")}
          >
            Confirm split
          </Button>
        </div>
        <p className="text-sm text-muted">
          {summary.unassigned > 0
            ? "Choose who had every item first."
            : "Items lock after this. You can still change who had what until the bill is closed."}
        </p>
      </div>
    </>
  );
}

function ProcessingView({
  createdAt,
  onManual,
}: {
  createdAt: string;
  onManual: () => Promise<boolean>;
}) {
  const [now, setNow] = useState(() => Date.now());
  const [switching, setSwitching] = useState(false);
  useEffect(() => {
    const t = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(t);
  }, []);
  const seconds = Math.max(0, Math.round((now - new Date(createdAt).getTime()) / 1000));

  return (
    <div className="rounded-xl border border-line bg-surface p-6">
      <p role="status" className="flex items-center gap-3 text-lg font-semibold">
        <span className="size-5 animate-spin rounded-full border-2 border-line-strong border-t-ink motion-reduce:animate-none" />
        Reading the receipt
      </p>
      <p className="mt-2 text-sm text-ink-soft">
        Finding the items and guessing who had each one. This usually takes under 30 seconds.
      </p>
      {seconds > 45 && (
        <p className="mt-2 text-sm text-ink-soft">
          Taking longer than usual - the server may have been asleep and is starting up.
        </p>
      )}
      <div className="mt-4">
        <Button
          type="button"
          variant="secondary"
          busy={switching}
          onClick={async () => {
            setSwitching(true);
            await onManual();
            setSwitching(false);
          }}
        >
          Type it in instead
        </Button>
      </div>
    </div>
  );
}

function DeleteBill({ billId, groupId }: { billId: string; groupId: string }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  return (
    <div className="mt-12 border-t border-line pt-6">
      <ConfirmButton
        label="Delete this bill"
        confirmLabel="Yes, delete it"
        busy={busy}
        onConfirm={async () => {
          setBusy(true);
          try {
            await api.deleteBill(billId);
            router.push(`/groups/${groupId}`);
          } catch (e) {
            setError(errorMessage(e));
            setBusy(false);
          }
        }}
      />
      {error && (
        <div className="mt-2">
          <Notice tone="error">{error}</Notice>
        </div>
      )}
    </div>
  );
}
