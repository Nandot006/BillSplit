// Browser-side Supabase client (design.md §14: "Supabase's official Next.js
// SSR client, storing the session in cookies"). Use this in Client
// Components only — Server Components/Route Handlers use `server.ts`
// instead, since they read/write cookies differently.

import { createBrowserClient } from "@supabase/ssr";

import { env } from "@/lib/env";

export function createClient() {
  return createBrowserClient(env.supabaseUrl, env.supabaseAnonKey);
}
