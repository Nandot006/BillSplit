"use client";

import type { Person } from "@billsplit/shared-types";
import { useState, type FormEvent } from "react";

import { useCurrentUser } from "@/components/current-user";
import {
  Avatar,
  Button,
  ButtonLink,
  Field,
  Loading,
  Notice,
  PageHeader,
  Section,
} from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import { summarizeTaste, type TasteSummary } from "@/lib/taxonomy";
import { useResource } from "@/lib/use-resource";

async function loadProfile(personId: string) {
  const [person, scores] = await Promise.all([
    api.getPerson(personId),
    api.getTasteScores(personId),
  ]);
  const group = await api.getGroup(person.group_id);
  return { person, groupName: group.name, taste: summarizeTaste(scores) };
}

export function ProfileScreen({ personId }: { personId: string }) {
  const user = useCurrentUser();
  const resource = useResource(() => loadProfile(personId), [personId]);

  if (resource.loading && !resource.data) return <Loading label="Loading profile" />;
  if (!resource.data)
    return <Notice tone="error">{resource.error ?? "Couldn't load this profile."}</Notice>;

  const { person, groupName, taste } = resource.data;
  const isMe = person.supabase_user_id === user.id;
  const groupPath = `/groups/${person.group_id}`;
  const questionnairePath = `/people/${person.id}/questionnaire?next=${encodeURIComponent(`/people/${person.id}`)}`;

  return (
    <>
      <PageHeader
        title={
          <span className="flex items-center gap-3">
            <Avatar name={person.display_name} />
            {isMe ? `${person.display_name} (you)` : person.display_name}
          </span>
        }
        back={{ href: groupPath, label: groupName }}
      >
        <p className="text-sm text-ink-soft">
          {person.supabase_user_id
            ? isMe
              ? `Your profile in ${groupName}. Your tastes can differ from group to group, so each group keeps its own.`
              : `Has a BillSplit account.`
            : `Added by name, without an account. Anyone in ${groupName} can keep this profile up to date.`}
        </p>
      </PageHeader>

      <Section
        title="Taste profile"
        aside={
          <ButtonLink
            href={questionnairePath}
            variant={taste.hasQuestionnaire ? "quiet" : "primary"}
          >
            {taste.hasQuestionnaire ? "Retake questionnaire" : "Fill in questionnaire"}
          </ButtonLink>
        }
      >
        <TasteCard taste={taste} />
      </Section>

      <DetailsForm
        key={`${person.id}:${person.display_name}:${person.free_text_preferences ?? ""}`}
        person={person}
        onSaved={(p) => resource.setData({ ...resource.data!, person: p })}
      />
    </>
  );
}

function TasteCard({ taste }: { taste: TasteSummary }) {
  if (!taste.hasQuestionnaire && taste.learnedFromCorrections === 0) {
    return (
      <p className="rounded-xl border border-dashed border-line-strong px-4 py-6 text-sm text-ink-soft">
        Nothing yet. Fill in the questionnaire so BillSplit can guess this person&apos;s items. It
        also learns every time you fix a guess on a bill.
      </p>
    );
  }
  return (
    <dl className="grid gap-4 rounded-xl border border-line bg-surface p-4 sm:grid-cols-3">
      <TasteList label="Never assigned" values={taste.restrictions} empty="No restrictions" />
      <TasteList label="Likely to order" values={taste.likes} empty="Nothing stands out yet" />
      <TasteList label="Unlikely to order" values={taste.dislikes} empty="Nothing stands out yet" />
      {taste.learnedFromCorrections > 0 && (
        <p className="text-xs text-muted sm:col-span-3">
          Refined by {taste.learnedFromCorrections} correction
          {taste.learnedFromCorrections === 1 ? "" : "s"} on past bills.
        </p>
      )}
    </dl>
  );
}

function TasteList({ label, values, empty }: { label: string; values: string[]; empty: string }) {
  return (
    <div>
      <dt className="mb-1 text-sm font-semibold text-ink-soft">{label}</dt>
      <dd className="flex flex-wrap gap-1.5">
        {values.length === 0 ? (
          <span className="text-sm text-muted">{empty}</span>
        ) : (
          values.map((v) => (
            <span key={v} className="rounded-full border border-line-strong px-2.5 py-0.5 text-sm">
              {v}
            </span>
          ))
        )}
      </dd>
    </div>
  );
}

function DetailsForm({ person, onSaved }: { person: Person; onSaved: (p: Person) => void }) {
  const [name, setName] = useState(person.display_name);
  const [notes, setNotes] = useState(person.free_text_preferences ?? "");
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<{ tone: "success" | "error"; text: string } | null>(null);

  const dirty =
    name.trim() !== person.display_name || notes.trim() !== (person.free_text_preferences ?? "");

  async function save(event: FormEvent) {
    event.preventDefault();
    setSaving(true);
    setMessage(null);
    try {
      const updated = await api.updatePerson(person.id, {
        display_name: name.trim(),
        free_text_preferences: notes.trim() || null,
      });
      onSaved(updated);
      setMessage({ tone: "success", text: "Saved." });
    } catch (e) {
      setMessage({ tone: "error", text: errorMessage(e) });
    } finally {
      setSaving(false);
    }
  }

  return (
    <Section title="Details">
      <form onSubmit={save} className="flex flex-col gap-4">
        <Field
          label="Name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          required
          maxLength={200}
        />
        <label className="flex flex-col gap-1 text-sm">
          <span className="font-medium text-ink-soft">Notes on food preferences</span>
          <textarea
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            rows={3}
            placeholder="e.g. Always orders filter coffee. Allergic to shellfish."
            className="rounded-lg border border-line-strong bg-surface px-3 py-2 text-base text-ink placeholder:text-muted"
          />
          <span className="text-xs text-muted">
            For people to read - guesses use the questionnaire, not these notes.
          </span>
        </label>
        {message && <Notice tone={message.tone}>{message.text}</Notice>}
        <div>
          <Button type="submit" busy={saving} disabled={!dirty || !name.trim()}>
            Save changes
          </Button>
        </div>
      </form>
    </Section>
  );
}
