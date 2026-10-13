// Server-side Supabase client for Server Components, Server Actions, and
// Route Handlers. Reads/writes the session cookie via `next/headers`, per
// the official @supabase/ssr Next.js App Router pattern.
//
// Server Components can't write cookies (Next.js throws), so `setAll` below
// is wrapped in a try/catch — that's safe only because `middleware.ts`
// refreshes the session on every request and writes the cookie there
// instead. Don't remove the middleware refresh without moving cookie
// writes somewhere that can actually perform them.

import { createServerClient } from "@supabase/ssr";
import { cookies } from "next/headers";

import { env } from "@/lib/env";

export async function createClient() {
  const cookieStore = await cookies();

  return createServerClient(env.supabaseUrl, env.supabaseAnonKey, {
    cookies: {
      getAll() {
        return cookieStore.getAll();
      },
      setAll(cookiesToSet) {
        try {
          for (const { name, value, options } of cookiesToSet) {
            cookieStore.set(name, value, options);
          }
        } catch {
          // Called from a Server Component - middleware.ts handles the
          // actual refresh/write for this request instead.
        }
      },
    },
  });
}
