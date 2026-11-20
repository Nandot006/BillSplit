"use client";

import type { Bill, GroupDetail, Person } from "@billsplit/shared-types";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import { ConfirmButton } from "@/components/confirm-button";
import { useCurrentUser } from "@/components/current-user";
import {
  Avatar,
  Button,
  ButtonLink,
  Loading,
  Notice,
  PageHeader,
  Section,
  inputClass,
} from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import { STATUS_LABELS } from "@/lib/bill";
import { formatMoney } from "@/lib/money";
import { useResource } from "@/lib/use-resource";

interface GroupData {
  group: GroupDetail;
  bills: Bill[];
  /** person id -> has filled in the taste questionnaire */
  profiled: Record<string, boolean>;
}

async function loadGroup(groupId: string): Promise<GroupData> {
  const [group, bills] = await Promise.all([api.getGroup(groupId), api.listBills(groupId)]);
  const scores = await Promise.all(group.people.map((p) => api.getTasteScores(p.id)));
  const profiled: Record<string, boolean> = {};
  group.people.forEach((p, i) => {
    profiled[p.id] = scores[i].some((s) => s.source === "questionnaire");
  });
  return { group, bills, profiled };
}

export function GroupScreen({ groupId }: { groupId: string }) {
  const user = useCurrentUser();
  const resource = useResource(() => loadGroup(groupId), [groupId]);

  if (resource.loading && !resource.data) return <Loading label="Loading group" />;
  if (!resource.data) {
    return <Notice tone="error">{resource.error ?? "Couldn't load this group."}</Notice>;
  }

  const { group, bills, profiled } = resource.data;
  const isCreator = group.creator_user_id === user.id;
  const me = group.people.find((p) => p.supabase_user_id === user.id);

  return (
    <>
      <PageHeader
        title={group.name}
        back={{ href: "/dashboard", label: "Your groups" }}
        actions={
          group.people.length > 0 ? (
            <ButtonLink href={`/groups/${group.id}/bills/new`}>New bill</ButtonLink>
          ) : undefined
        }
      />

      {me && !profiled[me.id] && (
        <div className="mb-6">
          <Notice tone="attention">
            BillSplit guesses who ordered what from everyone&apos;s tastes.{" "}
            <Link
              href={`/people/${me.id}/questionnaire?next=${encodeURIComponent(`/groups/${group.id}`)}`}
              className="font-semibold underline"
            >
              Tell it what you usually order
            </Link>
          </Notice>
        </div>
      )}

      <BillsSection group={group} bills={bills} />
      <MembersSection
        group={group}
        profiled={profiled}
        isCreator={isCreator}
        currentUserId={user.id}
        onChange={resource.reload}
      />
      {isCreator && <GroupSettings group={group} onRenamed={resource.reload} />}
    </>
  );
}

function BillsSection({ group, bills }: { group: GroupDetail; bills: Bill[] }) {
  const people = new Map(group.people.map((p) => [p.id, p.display_name]));
  return (
    <Section title="Bills">
      {bills.length === 0 ? (
        <div className="rounded-xl border border-dashed border-line-strong px-5 py-8 text-center">
          <p className="font-semibold">No bills yet</p>
          <p className="mt-1 text-sm text-ink-soft">
            After your next meal, tap New bill and take a photo of the receipt.
          </p>
        </div>
      ) : (
        <ul className="divide-y divide-line overflow-hidden rounded-xl border border-line bg-surface">
          {bills.map((bill) => {
            const needsYou = bill.status === "needs_review" || bill.status === "needs_manual_entry";
            return (
              <li key={bill.id}>
                <Link
                  href={`/bills/${bill.id}`}
                  className="flex items-center justify-between gap-4 px-4 py-3 hover:bg-paper"
                >
                  <span className="min-w-0">
                    <span className="block truncate font-semibold">
                      {bill.merchant_name || "Untitled bill"}
                    </span>
                    <span className="text-sm text-muted">
                      {formatDate(bill.bill_date ?? bill.created_at)} ·{" "}
                      {bill.participant_person_ids.length} people
                      {bill.payer_person_id &&
                        ` · paid by ${people.get(bill.payer_person_id) ?? "someone"}`}
                    </span>
                  </span>
                  <span className="shrink-0 text-right">
                    <span className="amount block font-semibold">
                      {bill.grand_total ? formatMoney(bill.grand_total) : "–"}
                    </span>
                    <span
                      className={`text-xs ${needsYou ? "rounded bg-highlight px-1.5 py-0.5 text-highlight-ink" : bill.status === "closed" ? "text-stamp" : "text-muted"}`}
                    >
                      {STATUS_LABELS[bill.status]}
                    </span>
                  </span>
                </Link>
              </li>
            );
          })}
        </ul>
      )}
    </Section>
  );
}

function MembersSection({
  group,
  profiled,
  isCreator,
  currentUserId,
  onChange,
}: {
  group: GroupDetail;
  profiled: Record<string, boolean>;
  isCreator: boolean;
  currentUserId: string;
  onChange: () => Promise<void>;
}) {
  const router = useRouter();
  const [name, setName] = useState("");
  const [adding, setAdding] = useState(false);
  const [removingId, setRemovingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function addMember(event: FormEvent) {
    event.preventDefault();
    if (!name.trim()) return;
    setAdding(true);
    setError(null);
    try {
      const person = await api.addPerson(group.id, { display_name: name.trim() });
      // design.md §4: the questionnaire runs whenever a contact is added.
      router.push(
        `/people/${person.id}/questionnaire?next=${encodeURIComponent(`/groups/${group.id}`)}`,
      );
    } catch (e) {
      setError(errorMessage(e));
      setAdding(false);
    }
  }

  async function removeMember(person: Person) {
    setRemovingId(person.id);
    setError(null);
    try {
      await api.removePerson(group.id, person.id);
      await onChange();
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setRemovingId(null);
    }
  }

  return (
    <Section title={`People (${group.people.length})`}>
      <ul className="mb-4 divide-y divide-line overflow-hidden rounded-xl border border-line bg-surface">
        {group.people.map((person) => {
          const isMe = person.supabase_user_id === currentUserId;
          return (
            <li key={person.id} className="flex items-center gap-3 px-4 py-3">
              <Avatar name={person.display_name} />
              <Link href={`/people/${person.id}`} className="min-w-0 flex-1 hover:underline">
                <span className="block truncate font-semibold">
                  {person.display_name}
                  {isMe && <span className="ml-2 text-sm font-normal text-muted">you</span>}
                </span>
                <span className="text-sm text-muted">
                  {profiled[person.id] ? "Taste profile set" : "No taste profile yet"}
                  {!person.supabase_user_id && " · no account"}
                </span>
              </Link>
              {isCreator && !isMe && (
                <ConfirmButton
                  label="Remove"
                  confirmLabel={`Remove ${person.display_name}`}
                  variant="quiet"
                  busy={removingId === person.id}
                  onConfirm={() => removeMember(person)}
                />
              )}
            </li>
          );
        })}
      </ul>

      {isCreator ? (
        <form onSubmit={addMember} className="flex flex-col gap-2 sm:flex-row">
          <label className="sr-only" htmlFor="member-name">
            Name of person to add
          </label>
          <input
            id="member-name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Friend's name"
            maxLength={200}
            className={`${inputClass} flex-1`}
          />
          <Button type="submit" variant="secondary" busy={adding} disabled={!name.trim()}>
            Add person
          </Button>
        </form>
      ) : (
        <p className="text-sm text-muted">
          Only the person who created this group can add or remove people.
        </p>
      )}
      {error && (
        <div className="mt-3">
          <Notice tone="error">{error}</Notice>
        </div>
      )}
    </Section>
  );
}

function GroupSettings({
  group,
  onRenamed,
}: {
  group: GroupDetail;
  onRenamed: () => Promise<void>;
}) {
  const router = useRouter();
  const [name, setName] = useState(group.name);
  const [busy, setBusy] = useState<"rename" | "delete" | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function rename(event: FormEvent) {
    event.preventDefault();
    setBusy("rename");
    setError(null);
    try {
      await api.renameGroup(group.id, name.trim());
      await onRenamed();
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(null);
    }
  }

  async function remove() {
    setBusy("delete");
    setError(null);
    try {
      await api.deleteGroup(group.id);
      router.push("/dashboard");
    } catch (e) {
      setError(errorMessage(e));
      setBusy(null);
    }
  }

  return (
    <Section title="Group settings">
      <form onSubmit={rename} className="mb-4 flex flex-col gap-2 sm:flex-row">
        <label className="sr-only" htmlFor="rename-group">
          Group name
        </label>
        <input
          id="rename-group"
          value={name}
          onChange={(e) => setName(e.target.value)}
          maxLength={200}
          className={`${inputClass} flex-1`}
        />
        <Button
          type="submit"
          variant="secondary"
          busy={busy === "rename"}
          disabled={!name.trim() || name.trim() === group.name}
        >
          Rename
        </Button>
      </form>
      <ConfirmButton
        label="Delete group"
        confirmLabel="Delete group and all its bills"
        busy={busy === "delete"}
        onConfirm={remove}
      />
      {error && (
        <div className="mt-3">
          <Notice tone="error">{error}</Notice>
        </div>
      )}
    </Section>
  );
}

function formatDate(value: string): string {
  const date = new Date(value.length === 10 ? `${value}T00:00:00` : value);
  return date.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}
