import Link from "next/link";
import { redirect } from "next/navigation";

import { CurrentUserProvider } from "@/components/current-user";
import { createClient } from "@/lib/supabase/server";

import { logout } from "../(auth)/actions";

export default async function AppLayout({ children }: { children: React.ReactNode }) {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  // proxy.ts already redirects logged-out requests; this is the backstop.
  if (!user) redirect("/login");

  return (
    <CurrentUserProvider user={{ id: user.id, email: user.email ?? null }}>
      <div className="border-b border-line bg-surface">
        <div className="mx-auto flex max-w-2xl items-center justify-between px-4 py-3">
          <Link
            href="/dashboard"
            className="font-[family-name:var(--font-display)] text-xl font-bold"
          >
            BillSplit
          </Link>
          <form action={logout} className="flex items-center gap-3 text-sm text-ink-soft">
            <span className="hidden sm:inline">{user.email}</span>
            <button type="submit" className="font-semibold text-ink hover:underline">
              Log out
            </button>
          </form>
        </div>
      </div>
      <main className="mx-auto w-full max-w-2xl flex-1 px-4 py-8">{children}</main>
    </CurrentUserProvider>
  );
}
