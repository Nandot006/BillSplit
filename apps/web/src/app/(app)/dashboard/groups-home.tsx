"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import { useCurrentUser } from "@/components/current-user";
import { Button, Loading, Notice, PageHeader, inputClass } from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import { useResource } from "@/lib/use-resource";

export function GroupsHome() {
  const router = useRouter();
  const user = useCurrentUser();
  const groups = useResource(() => api.listGroups(), []);
  const [name, setName] = useState("");
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function createGroup(event: FormEvent) {
    event.preventDefault();
    if (!name.trim()) return;
    setCreating(true);
    setError(null);
    try {
      const group = await api.createGroup(name.trim());
      // You're added to every group you create. Your taste profile is per
      // group (design.md §2), so start this one with the questionnaire.
      const detail = await api.getGroup(group.id);
      const me = detail.people.find((p) => p.supabase_user_id === user.id);
      const groupPath = `/groups/${group.id}`;
      router.push(
        me ? `/people/${me.id}/questionnaire?next=${encodeURIComponent(groupPath)}` : groupPath,
      );
    } catch (e) {
      setError(errorMessage(e));
      setCreating(false);
    }
  }

  const list = groups.data ?? [];

  return (
    <>
      <PageHeader title="Your groups">
        <p className="text-ink-soft">
          A group is the people you usually eat out with. Each bill is split between whoever in the
          group was there.
        </p>
      </PageHeader>

      <form onSubmit={createGroup} className="mb-8 flex flex-col gap-2 sm:flex-row">
        <label className="sr-only" htmlFor="group-name">
          New group name
        </label>
        <input
          id="group-name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="e.g. Hostel lunch gang"
          maxLength={200}
          className={`${inputClass} flex-1`}
        />
        <Button type="submit" busy={creating} disabled={!name.trim()}>
          Create group
        </Button>
      </form>
      {error && (
        <div className="-mt-6 mb-6">
          <Notice tone="error">{error}</Notice>
        </div>
      )}

      {groups.loading && !groups.data ? (
        <Loading label="Loading your groups" />
      ) : groups.error && !groups.data ? (
        <Notice tone="error">
          {groups.error}{" "}
          <button className="font-semibold underline" onClick={() => void groups.reload()}>
            Try again
          </button>
        </Notice>
      ) : list.length === 0 ? (
        <div className="rounded-xl border border-dashed border-line-strong px-5 py-10 text-center">
          <p className="font-semibold">No groups yet</p>
          <p className="mt-1 text-sm text-ink-soft">
            Create one above, add your friends, then snap your first receipt.
          </p>
        </div>
      ) : (
        <ul className="divide-y divide-line overflow-hidden rounded-xl border border-line bg-surface">
          {list.map((group) => (
            <li key={group.id}>
              <Link
                href={`/groups/${group.id}`}
                className="flex items-center justify-between px-4 py-4 hover:bg-paper"
              >
                <span className="font-semibold">{group.name}</span>
                <span className="text-sm text-muted">
                  {group.creator_user_id === user.id ? "You created this" : "Member"}
                </span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </>
  );
}
