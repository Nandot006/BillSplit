import { logout } from "../(auth)/actions";
import { createClient } from "@/lib/supabase/server";

export default async function DashboardPage() {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-4 px-4 py-16">
      <h1 className="text-xl font-semibold">Dashboard</h1>
      <p className="text-sm text-zinc-500">
        Signed in as <span className="font-medium text-foreground">{user?.email}</span>.
      </p>
      <p className="text-sm text-zinc-500">
        Groups and bills land here in later blocks (Phase 2 Blocks 3 &amp; 5).
      </p>
      <form action={logout}>
        <button
          type="submit"
          className="w-fit rounded-md border border-zinc-300 px-4 py-2 text-sm font-medium dark:border-zinc-700"
        >
          Log out
        </button>
      </form>
    </div>
  );
}
